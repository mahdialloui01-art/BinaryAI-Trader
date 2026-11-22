from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


ENGINE_VERSION = "2.2.0"
INTERVAL_SECONDS = {"1m": 60, "5m": 300, "15m": 900, "30m": 1800, "1h": 3600, "4h": 14400}


def _ema(values: list[float], period: int) -> list[float]:
    if not values:
        return []
    alpha = 2.0 / (period + 1)
    out = [values[0]]
    for value in values[1:]:
        out.append(alpha * value + (1.0 - alpha) * out[-1])
    return out


def _wilder(values: list[float], period: int) -> list[float]:
    if not values:
        return []
    out = [float("nan")] * len(values)
    if len(values) < period:
        return out
    seed = sum(values[:period]) / period
    out[period - 1] = seed
    for i in range(period, len(values)):
        out[i] = (out[i - 1] * (period - 1) + values[i]) / period
    return out


def _rsi(closes: list[float], period: int = 14) -> float | None:
    if len(closes) <= period:
        return None
    changes = [b - a for a, b in zip(closes, closes[1:])]
    gains = [max(x, 0.0) for x in changes]
    losses = [max(-x, 0.0) for x in changes]
    avg_g, avg_l = _wilder(gains, period)[-1], _wilder(losses, period)[-1]
    if avg_l == 0:
        return 100.0 if avg_g > 0 else 50.0
    return 100.0 - 100.0 / (1.0 + avg_g / avg_l)


def _true_ranges(bars: list[dict[str, Any]]) -> list[float]:
    values = []
    for i, bar in enumerate(bars):
        high, low = bar["high"], bar["low"]
        previous = bars[i - 1]["close"] if i else bar["close"]
        values.append(max(high - low, abs(high - previous), abs(low - previous)))
    return values


def _adx(bars: list[dict[str, Any]], period: int = 14) -> tuple[float | None, float | None, float | None]:
    if len(bars) < period * 2 + 1:
        return None, None, None
    plus_dm, minus_dm = [], []
    for prev, cur in zip(bars, bars[1:]):
        up, down = cur["high"] - prev["high"], prev["low"] - cur["low"]
        plus_dm.append(up if up > down and up > 0 else 0.0)
        minus_dm.append(down if down > up and down > 0 else 0.0)
    tr = _wilder(_true_ranges(bars)[1:], period)
    plus = _wilder(plus_dm, period)
    minus = _wilder(minus_dm, period)
    dx = []
    last_pdi = last_mdi = None
    for i in range(len(tr)):
        if i >= len(plus) or tr[i] != tr[i] or tr[i] <= 0 or plus[i] != plus[i] or minus[i] != minus[i]:
            dx.append(0.0)
            continue
        pdi, mdi = 100.0 * plus[i] / tr[i], 100.0 * minus[i] / tr[i]
        last_pdi, last_mdi = pdi, mdi
        dx.append(100.0 * abs(pdi - mdi) / max(pdi + mdi, 1e-12))
    smooth = _wilder(dx, period)
    value = smooth[-1] if smooth and smooth[-1] == smooth[-1] else None
    return value, last_pdi, last_mdi


def _valid_candles(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    valid: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        try:
            o, h, low, c = (float(row[k]) for k in ("open", "high", "low", "close"))
        except (KeyError, TypeError, ValueError):
            continue
        if min(o, h, low, c) <= 0 or h < max(o, c, low) or low > min(o, c, h):
            continue
        stamp = row.get("timestamp", row.get("time", row.get("openTime")))
        stamp_key = str(stamp) if stamp is not None else None
        if stamp_key and stamp_key in seen:
            continue
        if stamp_key:
            seen.add(stamp_key)
        valid.append({"open": o, "high": h, "low": low, "close": c, "timestamp": stamp})
    return valid


def _market_structure(bars: list[dict[str, Any]], wing: int = 2) -> dict[str, Any]:
    highs, lows = [], []
    for i in range(wing, len(bars) - wing):
        if all(bars[i]["high"] > bars[j]["high"] for j in range(i-wing, i+wing+1) if j != i):
            highs.append((i, bars[i]["high"]))
        if all(bars[i]["low"] < bars[j]["low"] for j in range(i-wing, i+wing+1) if j != i):
            lows.append((i, bars[i]["low"]))
    hh = len(highs) >= 2 and highs[-1][1] > highs[-2][1]
    hl = len(lows) >= 2 and lows[-1][1] > lows[-2][1]
    lh = len(highs) >= 2 and highs[-1][1] < highs[-2][1]
    ll = len(lows) >= 2 and lows[-1][1] < lows[-2][1]
    last = bars[-1]
    previous_high = highs[-1][1] if highs else None
    previous_low = lows[-1][1] if lows else None
    bos_up = previous_high is not None and last["close"] > previous_high
    bos_down = previous_low is not None and last["close"] < previous_low
    return {
        "swing_highs": [round(x[1], 8) for x in highs[-3:]],
        "swing_lows": [round(x[1], 8) for x in lows[-3:]],
        "structure": "BULLISH" if hh and hl else "BEARISH" if lh and ll else "RANGING_OR_TRANSITION",
        "bos": "BULLISH" if bos_up else "BEARISH" if bos_down else None,
        "higher_high": hh, "higher_low": hl, "lower_high": lh, "lower_low": ll,
    }


def _candle_context(bars: list[dict[str, Any]]) -> dict[str, Any]:
    c, p = bars[-1], bars[-2]
    rng = max(c["high"] - c["low"], 1e-12)
    body = abs(c["close"] - c["open"])
    upper = c["high"] - max(c["open"], c["close"])
    lower = min(c["open"], c["close"]) - c["low"]
    bull_engulf = (p["close"] < p["open"] and c["close"] > c["open"]
                   and c["open"] <= p["close"] and c["close"] >= p["open"])
    bear_engulf = (p["close"] > p["open"] and c["close"] < c["open"]
                   and c["open"] >= p["close"] and c["close"] <= p["open"])
    bull_pin = lower / rng >= 0.58 and body / rng <= 0.36 and upper / rng <= 0.22
    bear_pin = upper / rng >= 0.58 and body / rng <= 0.36 and lower / rng <= 0.22
    return {
        "body_ratio": body / rng, "upper_wick_ratio": upper / rng,
        "lower_wick_ratio": lower / rng,
        "pattern": "BULL_ENGULFING" if bull_engulf else "BEAR_ENGULFING" if bear_engulf
                   else "BULL_REJECTION" if bull_pin else "BEAR_REJECTION" if bear_pin else "NONE",
        "bullish": bull_engulf or bull_pin, "bearish": bear_engulf or bear_pin,
    }


def _fvg(bars: list[dict[str, Any]]) -> dict[str, Any] | None:
    # Three-candle imbalance; only zones formed by already closed candles are considered.
    for i in range(len(bars) - 1, max(1, len(bars) - 12), -1):
        left, right = bars[i - 2], bars[i]
        if right["low"] > left["high"]:
            return {"type": "BULLISH", "low": left["high"], "high": right["low"], "index": i}
        if right["high"] < left["low"]:
            return {"type": "BEARISH", "low": right["high"], "high": left["low"], "index": i}
    return None



def _market_regime(bars: list[dict[str, Any]]) -> dict[str, Any]:
    """Classify trend efficiency and volatility expansion without fitting on future bars."""
    closes = [bar["close"] for bar in bars]
    window = min(20, len(closes) - 1)
    path = sum(abs(closes[i] - closes[i - 1]) for i in range(len(closes) - window, len(closes)))
    net = abs(closes[-1] - closes[-1 - window])
    efficiency = net / max(path, 1e-12)

    tr = _true_ranges(bars)
    atr_series = _wilder(tr, 14)
    valid_atr = [value for value in atr_series[-60:] if value == value and value > 0]
    current_atr = valid_atr[-1] if valid_atr else None
    baseline = sorted(valid_atr[:-1]) if len(valid_atr) > 1 else []
    median_atr = (baseline[len(baseline) // 2] if len(baseline) % 2 else
                  (baseline[len(baseline) // 2 - 1] + baseline[len(baseline) // 2]) / 2
                  if baseline else None)
    volatility_ratio = current_atr / median_atr if current_atr and median_atr else None
    volatility_state = (
        "EXPANSION" if volatility_ratio is not None and volatility_ratio >= 2.5 else
        "COMPRESSION" if volatility_ratio is not None and volatility_ratio <= 0.45 else
        "NORMAL" if volatility_ratio is not None else "UNAVAILABLE"
    )
    trend_state = "DIRECTIONAL" if efficiency >= 0.35 else "MIXED" if efficiency >= 0.18 else "CHOPPY"
    return {
        "trend_efficiency_20": round(efficiency, 4),
        "volatility_ratio_to_recent_median": round(volatility_ratio, 3) if volatility_ratio is not None else None,
        "volatility_state": volatility_state,
        "trend_state": trend_state,
        "method": "20-bar Kaufman-style efficiency ratio and current Wilder ATR versus recent median",
    }


def _time_quality(bars: list[dict[str, Any]], interval: str, as_of: datetime | None = None) -> dict[str, Any]:
    stamps = []
    for bar in bars:
        raw = bar.get("timestamp")
        try:
            if isinstance(raw, (int, float)):
                from datetime import timedelta
                stamp = datetime.fromtimestamp(raw / 1000 if raw > 10_000_000_000 else raw, timezone.utc)
            elif raw:
                stamp = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
                if stamp.tzinfo is None:
                    stamp = stamp.replace(tzinfo=timezone.utc)
                stamp = stamp.astimezone(timezone.utc)
            else:
                stamp = None
        except (ValueError, TypeError, OverflowError, OSError):
            stamp = None
        if stamp:
            stamps.append(stamp)
    seconds = INTERVAL_SECONDS.get(interval, 60)
    gaps = 0
    if len(stamps) > 1:
        for a, b in zip(stamps, stamps[1:]):
            delta = (b - a).total_seconds()
            if delta > seconds * 1.5:
                gaps += max(1, round(delta / seconds) - 1)
    reference_time = as_of or datetime.now(timezone.utc)
    latest_age = max(0.0, (reference_time - stamps[-1]).total_seconds()) if stamps else None
    return {
        "timestamped_bars": len(stamps), "timestamp_coverage": round(len(stamps) / max(1, len(bars)), 4), "missing_bars_estimate": gaps,
        "latest_closed_bar_age_seconds": round(latest_age, 2) if latest_age is not None else None,
        "stale": latest_age is None or latest_age > seconds * 3.5 or len(stamps) / max(1, len(bars)) < 0.98,
        "gap_ratio": gaps / max(1, len(bars) + gaps),
    }


def _timeframe_bias(rows: list[dict[str, Any]], interval: str, as_of: datetime | None = None) -> dict[str, Any]:
    bars = _valid_candles(rows)
    if len(bars) < 55:
        return {"bias": "UNAVAILABLE", "bars": len(bars), "quality": _time_quality(bars, interval, as_of)}
    closes = [x["close"] for x in bars]
    e21, e50 = _ema(closes, 21), _ema(closes, 50)
    slope = e21[-1] - e21[-5]
    bias = "BULLISH" if e21[-1] > e50[-1] and slope > 0 else "BEARISH" if e21[-1] < e50[-1] and slope < 0 else "NEUTRAL"
    return {"bias": bias, "ema21": round(e21[-1], 8), "ema50": round(e50[-1], 8), "bars": len(bars), "quality": _time_quality(bars, interval, as_of)}



def _directional_horizon_forecasts(
    bars: list[dict[str, Any]],
    interval: str,
    higher_timeframes: dict[str, dict[str, Any]],
    quality: dict[str, Any],
) -> dict[str, Any]:
    """Evidence-weighted outlooks for the next 1, 2 and 5 minutes; not probabilities."""
    closes = [bar["close"] for bar in bars]
    seconds = INTERVAL_SECONDS.get(interval, 60)
    horizons = {}
    ema_fast, ema_slow, ema_base = _ema(closes, 9), _ema(closes, 21), _ema(closes, 50)
    atr_values = _wilder(_true_ranges(bars), 14)
    atr = atr_values[-1] if atr_values and atr_values[-1] == atr_values[-1] else 0.0
    structure = _market_structure(bars)
    candle = _candle_context(bars)
    for minutes in (1, 2, 5):
        lookback = max(2, min(len(bars) - 2, round(minutes * 60 / seconds)))
        momentum_window = max(3, min(len(bars) - 2, lookback * 3))
        price = closes[-1]
        momentum = price - closes[-1 - momentum_window]
        normalized_momentum = momentum / max(atr * (momentum_window ** 0.5), 1e-12)
        ema_slope = ema_fast[-1] - ema_fast[max(0, len(ema_fast) - 1 - lookback)]
        trend = "CALL" if ema_fast[-1] > ema_slow[-1] and ema_slow[-1] >= ema_base[-1] and ema_slope > 0 else "PUT" if ema_fast[-1] < ema_slow[-1] and ema_slow[-1] <= ema_base[-1] and ema_slope < 0 else None
        momentum_dir = "CALL" if normalized_momentum > 0.10 else "PUT" if normalized_momentum < -0.10 else None
        structure_dir = "CALL" if structure["structure"] == "BULLISH" or structure["bos"] == "BULLISH" else "PUT" if structure["structure"] == "BEARISH" or structure["bos"] == "BEARISH" else None
        candle_dir = "CALL" if candle["bullish"] else "PUT" if candle["bearish"] else None
        mtf_biases = [item.get("bias") for item in higher_timeframes.values() if item.get("bias") in ("BULLISH", "BEARISH")]
        mtf_dir = "CALL" if len(mtf_biases) >= 2 and all(x == "BULLISH" for x in mtf_biases) else "PUT" if len(mtf_biases) >= 2 and all(x == "BEARISH" for x in mtf_biases) else None
        votes = [
            ("trend", trend, 30, "اتجاه EMA 9/21/50 وميل المتوسط السريع"),
            ("momentum", momentum_dir, 25, f"الزخم المعياري عبر {momentum_window} شموع"),
            ("structure", structure_dir, 20, f"بنية السوق {structure['structure']} / BOS {structure['bos'] or 'غير مؤكد'}"),
            ("candle", candle_dir, 10, f"سلوك آخر شمعة: {candle['pattern']}"),
            ("higher_timeframes", mtf_dir, 15, "توافق الأطر الأعلى" if mtf_dir else "الأطر الأعلى غير متوافقة بالكامل"),
        ]
        long_points = sum(weight for _, direction, weight, _ in votes if direction == "CALL")
        short_points = sum(weight for _, direction, weight, _ in votes if direction == "PUT")
        score, margin = max(long_points, short_points), abs(long_points - short_points)
        candidate = "CALL" if long_points > short_points else "PUT" if short_points > long_points else "NO_TRADE"
        blockers = []
        if quality.get("stale"): blockers.append("STALE_CLOSED_CANDLES")
        if quality.get("gap_ratio", 0) > 0.08: blockers.append("EXCESSIVE_CANDLE_GAPS")
        if atr <= 0: blockers.append("ATR_UNAVAILABLE")
        if score < 55: blockers.append("WEAK_HORIZON_CONFLUENCE")
        if margin < 20: blockers.append("HORIZON_DIRECTION_CONFLICT")
        if trend and momentum_dir and trend != momentum_dir: blockers.append("TREND_MOMENTUM_CONFLICT")
        decision = candidate if not blockers else "NO_TRADE"
        horizons[f"{minutes}m"] = {
            "horizon_minutes": minutes, "forecast_window": f"next_{minutes}_minutes",
            "decision": decision, "candidate": candidate, "score": score,
            "long_score": long_points, "short_score": short_points, "directional_margin": margin,
            "evidence": [{"module": name, "direction": direction or "NEUTRAL", "weight": weight if direction else 0, "detail": detail} for name, direction, weight, detail in votes],
            "blockers": blockers, "note": "درجة توافق الأدلة وليست احتمال نجاح أو ضماناً لاتجاه السعر.",
        }
    return horizons


def analyze_binary_options(
    candles: list[dict[str, Any]],
    symbol: str,
    interval: str = "1m",
    higher_timeframes: dict[str, list[dict[str, Any]]] | None = None,
    as_of: datetime | None = None,
) -> dict[str, Any]:
    """Multi-factor, closed-candle binary-options research. Score is confluence, never win probability."""
    bars = _valid_candles(candles)
    base = {
        "symbol": symbol, "provider": "deriv", "interval": interval,
        "execution_enabled": False, "engine_version": ENGINE_VERSION,
        "score_is_probability": False,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    if len(bars) < 120:
        return {**base, "decision": "NO_TRADE", "candidate": "NO_TRADE", "score": 0,
                "confidence": 0, "status": "insufficient_data", "candles_used": len(bars),
                "rationale": ["يلزم 120 شمعة مغلقة وصحيحة على الأقل."],
                "blockers": ["INSUFFICIENT_CLOSED_CANDLES"], "modules": {}}

    closes = [x["close"] for x in bars]
    highs, lows = [x["high"] for x in bars], [x["low"] for x in bars]
    last = bars[-1]
    e9, e21, e50, e100 = (_ema(closes, n) for n in (9, 21, 50, 100))
    rsi = _rsi(closes)
    macd = [a-b for a,b in zip(_ema(closes, 12), _ema(closes, 26))]
    macd_signal = _ema(macd, 9)
    macd_hist = macd[-1] - macd_signal[-1]
    adx, pdi, mdi = _adx(bars)
    tr = _true_ranges(bars)
    atr_series = _wilder(tr, 14)
    atr = atr_series[-1]
    atr_pct = atr / max(last["close"], 1e-12) * 100
    mean20 = sum(closes[-20:]) / 20
    std20 = (sum((x-mean20)**2 for x in closes[-20:]) / 20) ** 0.5
    bb_upper, bb_lower = mean20 + 2*std20, mean20 - 2*std20
    bb_width_pct = (bb_upper - bb_lower) / max(mean20, 1e-12) * 100
    structure = _market_structure(bars)
    candle = _candle_context(bars)
    fvg = _fvg(bars)
    prior_high, prior_low = max(highs[-21:-1]), min(lows[-21:-1])
    # Sweep = pierce a recent liquidity level then close back inside.
    sweep_high = last["high"] > prior_high and last["close"] < prior_high
    sweep_low = last["low"] < prior_low and last["close"] > prior_low
    momentum3 = last["close"] - closes[-4]
    momentum8 = last["close"] - closes[-9]
    ret5 = (closes[-1] / closes[-6] - 1) * 100
    ret20 = (closes[-1] / closes[-21] - 1) * 100
    mtf = {tf: _timeframe_bias(rows, tf, as_of) for tf, rows in (higher_timeframes or {}).items()}
    available_mtf = [x["bias"] for x in mtf.values() if x["bias"] != "UNAVAILABLE"]
    bull_mtf = sum(x == "BULLISH" for x in available_mtf)
    bear_mtf = sum(x == "BEARISH" for x in available_mtf)
    mtf_consensus = "BULLISH" if available_mtf and bull_mtf == len(available_mtf) else "BEARISH" if available_mtf and bear_mtf == len(available_mtf) else "MIXED" if available_mtf else "UNAVAILABLE"

    # Directional evidence is grouped by independent concepts to reduce duplicate-indicator voting.
    long_points = short_points = 0.0
    modules: dict[str, Any] = {}
    reasons: list[str] = []

    def add(name: str, direction: str | None, weight: float, detail: str):
        nonlocal long_points, short_points
        if direction == "CALL":
            long_points += weight
        elif direction == "PUT":
            short_points += weight
        modules[name] = {"direction": direction or "NEUTRAL", "weight": weight if direction else 0, "detail": detail}
        if direction:
            reasons.append(detail)

    trend_dir = "CALL" if e9[-1] > e21[-1] > e50[-1] and e21[-1] > e21[-5] else "PUT" if e9[-1] < e21[-1] < e50[-1] and e21[-1] < e21[-5] else None
    add("trend_structure", trend_dir, 18, "اتجاه المتوسطات 9/21/50 وميل EMA21 متوافق." if trend_dir else "اتجاه المتوسطات غير متراص.")
    structure_dir = "CALL" if structure["structure"] == "BULLISH" or structure["bos"] == "BULLISH" else "PUT" if structure["structure"] == "BEARISH" or structure["bos"] == "BEARISH" else None
    add("market_structure", structure_dir, 16, f"بنية السوق: {structure['structure']}، BOS: {structure['bos'] or 'لا يوجد'}.")
    momentum_dir = "CALL" if macd_hist > 0 and momentum3 > 0 and momentum8 > 0 else "PUT" if macd_hist < 0 and momentum3 < 0 and momentum8 < 0 else None
    add("momentum", momentum_dir, 14, f"MACD histogram={macd_hist:.8g}، عائد 5/20={ret5:.4f}%/{ret20:.4f}%.")
    rsi_dir = "CALL" if rsi is not None and 52 <= rsi <= 68 else "PUT" if rsi is not None and 32 <= rsi <= 48 else None
    add("rsi_regime", rsi_dir, 8, f"RSI14={rsi:.1f}." if rsi is not None else "RSI غير متاح.")
    di_dir = "CALL" if adx is not None and adx >= 18 and pdi is not None and pdi > mdi else "PUT" if adx is not None and adx >= 18 and mdi is not None and mdi > pdi else None
    add("trend_strength", di_dir, 10, f"ADX={adx:.1f}, +DI={pdi:.1f}, -DI={mdi:.1f}." if adx is not None else "ADX غير متاح.")
    candle_dir = "CALL" if candle["bullish"] else "PUT" if candle["bearish"] else None
    add("price_action", candle_dir, 8, f"نموذج الشمعة: {candle['pattern']}، نسبة الجسم {candle['body_ratio']:.2f}.")
    sweep_dir = "CALL" if sweep_low else "PUT" if sweep_high else None
    add("liquidity_sweep", sweep_dir, 10, "سحب سيولة أسفل قاع ثم إغلاق داخله." if sweep_low else "سحب سيولة أعلى قمة ثم إغلاق أسفلها." if sweep_high else "لا يوجد sweep مؤكد.")
    fvg_dir = "CALL" if fvg and fvg["type"] == "BULLISH" and fvg["low"] <= last["close"] <= fvg["high"] else "PUT" if fvg and fvg["type"] == "BEARISH" and fvg["low"] <= last["close"] <= fvg["high"] else None
    add("imbalance_fvg", fvg_dir, 6, f"منطقة FVG: {fvg['type']}." if fvg else "لا توجد فجوة قيمة عادلة حديثة.")
    mtf_dir = "CALL" if mtf_consensus == "BULLISH" else "PUT" if mtf_consensus == "BEARISH" else None
    add("multi_timeframe", mtf_dir, 10, f"توافق الأطر الأعلى: {mtf_consensus}.")

    total_weight = sum(x["weight"] for x in ({"weight": 18},{"weight":16},{"weight":14},{"weight":8},{"weight":10},{"weight":8},{"weight":10},{"weight":6},{"weight":10}))
    long_score, short_score = round(long_points / total_weight * 100), round(short_points / total_weight * 100)
    score = max(long_score, short_score)
    margin = abs(long_score - short_score)
    candidate = "CALL" if long_score > short_score else "PUT" if short_score > long_score else "NO_TRADE"
    quality = _time_quality(bars, interval, as_of)
    regime = _market_regime(bars)
    blockers = []
    if quality["stale"]:
        blockers.append("STALE_CLOSED_CANDLES")
    if quality["gap_ratio"] > 0.08:
        blockers.append("EXCESSIVE_CANDLE_GAPS")
    if len(available_mtf) < 2:
        blockers.append("INSUFFICIENT_HIGHER_TIMEFRAME_CONFIRMATION")
    if any(x.get("quality", {}).get("stale") for x in mtf.values() if x.get("bias") != "UNAVAILABLE"):
        blockers.append("STALE_HIGHER_TIMEFRAME_CANDLES")
    if any(x.get("quality", {}).get("gap_ratio", 0) > 0.08 for x in mtf.values() if x.get("bias") != "UNAVAILABLE"):
        blockers.append("HIGHER_TIMEFRAME_DATA_GAPS")
    if mtf_dir != candidate and candidate != "NO_TRADE":
        blockers.append("HIGHER_TIMEFRAME_CONFLICT")
    if adx is not None and adx < 12:
        blockers.append("VERY_WEAK_TREND_OR_CHOP")
    if regime["trend_state"] == "CHOPPY" and adx is not None and adx < 18:
        blockers.append("LOW_DIRECTIONAL_EFFICIENCY_CHOP")
    if regime["volatility_state"] == "EXPANSION":
        blockers.append("ABNORMAL_VOLATILITY_EXPANSION")
    if regime["volatility_state"] == "COMPRESSION":
        blockers.append("LOW_VOLATILITY_COMPRESSION")
    if atr_pct > 0.45:
        blockers.append("EXTREME_VOLATILITY")
    if bb_width_pct < 0.015:
        blockers.append("VOLATILITY_COMPRESSION")
    if candle["body_ratio"] < 0.12 and not candle["bullish"] and not candle["bearish"]:
        blockers.append("INDECISIVE_LAST_CANDLE")
    if sweep_high and candidate == "CALL":
        blockers.append("BEARISH_LIQUIDITY_SWEEP_CONFLICT")
    if sweep_low and candidate == "PUT":
        blockers.append("BULLISH_LIQUIDITY_SWEEP_CONFLICT")
    if score < 72:
        blockers.append("CONFLUENCE_BELOW_72")
    if margin < 22:
        blockers.append("DIRECTIONAL_EDGE_TOO_SMALL")

    decision = candidate if not blockers else "NO_TRADE"
    seconds = INTERVAL_SECONDS.get(interval, 60)
    expiry_candidates = [1, 2, 3]
    # Recommend a research horizon, never a broker contract instruction.
    if adx is not None and adx >= 25 and mtf_consensus == candidate:
        expiry_bars = 2
    elif adx is not None and adx < 18:
        expiry_bars = 1
    else:
        expiry_bars = 1
    return {
        **base, "decision": decision, "candidate": candidate,
        "score": score, "long_score": long_score, "short_score": short_score,
        "directional_margin": margin, "confidence": round(score / 100, 2),
        "status": "signal_candidate" if decision != "NO_TRADE" else "wait",
        "candles_used": len(bars), "latest_closed_candle": last.get("timestamp"),
        "quality": quality,
        "market_regime": regime,
        "indicators": {
            "ema9": round(e9[-1], 8), "ema21": round(e21[-1], 8),
            "ema50": round(e50[-1], 8), "ema100": round(e100[-1], 8),
            "rsi14": round(rsi, 2) if rsi is not None else None,
            "macd_histogram": round(macd_hist, 10), "adx14": round(adx, 2) if adx is not None else None,
            "plus_di": round(pdi, 2) if pdi is not None else None,
            "minus_di": round(mdi, 2) if mdi is not None else None,
            "atr14": round(atr, 10), "atr_percent": round(atr_pct, 5),
            "bollinger_upper": round(bb_upper, 8), "bollinger_middle": round(mean20, 8),
            "bollinger_lower": round(bb_lower, 8), "bollinger_width_percent": round(bb_width_pct, 5),
        },
        "market_structure": structure,
        "candle_analysis": candle,
        "liquidity": {"sweep_high": sweep_high, "sweep_low": sweep_low,
                      "reference_high": round(prior_high, 8), "reference_low": round(prior_low, 8)},
        "fair_value_gap": fvg,
        "higher_timeframes": mtf, "mtf_consensus": mtf_consensus,
        "horizon_forecasts": _directional_horizon_forecasts(bars, interval, mtf, quality),
        "modules": modules, "rationale": reasons, "blockers": blockers,
        "expiry_research": {"recommended_bars": expiry_bars, "seconds": expiry_bars * seconds,
                            "tested_alternatives_bars": expiry_candidates,
                            "note": "Horizon suggestion only; validate each expiry against actual payout and out-of-sample data."},
        "disclaimer": "Score measures rule confluence, not probability of winning. No profit or win-rate is promised. Validate by walk-forward and forward testing.",
    }
