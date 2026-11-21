from __future__ import annotations

from datetime import datetime, timezone
from math import sqrt
from typing import Any


def _ema(values: list[float], period: int) -> list[float]:
    if not values:
        return []
    alpha = 2.0 / (period + 1)
    out = [values[0]]
    for value in values[1:]:
        out.append(alpha * value + (1 - alpha) * out[-1])
    return out


def _rsi(values: list[float], period: int = 14) -> float | None:
    if len(values) <= period:
        return None
    changes = [b - a for a, b in zip(values, values[1:])]
    gains = [max(x, 0.0) for x in changes[-period:]]
    losses = [max(-x, 0.0) for x in changes[-period:]]
    avg_gain, avg_loss = sum(gains) / period, sum(losses) / period
    if avg_loss == 0:
        return 100.0 if avg_gain else 50.0
    rs = avg_gain / avg_loss
    return 100 - 100 / (1 + rs)


def _adx(candles: list[dict[str, Any]], period: int = 14) -> float | None:
    if len(candles) < period * 2 + 1:
        return None
    plus_dm, minus_dm, trs = [], [], []
    for prev, cur in zip(candles, candles[1:]):
        up = float(cur["high"]) - float(prev["high"])
        down = float(prev["low"]) - float(cur["low"])
        plus_dm.append(up if up > down and up > 0 else 0.0)
        minus_dm.append(down if down > up and down > 0 else 0.0)
        trs.append(max(float(cur["high"]) - float(cur["low"]),
                       abs(float(cur["high"]) - float(prev["close"])),
                       abs(float(cur["low"]) - float(prev["close"]))))
    dx = []
    for i in range(period - 1, len(trs)):
        tr = sum(trs[i - period + 1:i + 1])
        if tr <= 0:
            dx.append(0.0)
            continue
        pdi = 100 * sum(plus_dm[i - period + 1:i + 1]) / tr
        mdi = 100 * sum(minus_dm[i - period + 1:i + 1]) / tr
        dx.append(100 * abs(pdi - mdi) / max(pdi + mdi, 1e-9))
    return sum(dx[-period:]) / min(period, len(dx)) if dx else None


def _valid_candles(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    valid = []
    previous = None
    for row in rows:
        try:
            o, h, low, c = (float(row[k]) for k in ("open", "high", "low", "close"))
        except (KeyError, TypeError, ValueError):
            continue
        if min(o, h, low, c) <= 0 or h < max(o, c, low) or low > min(o, c, h):
            continue
        stamp = row.get("timestamp", row.get("time", row.get("openTime")))
        if stamp is not None and previous is not None and str(stamp) <= str(previous):
            continue
        if stamp is not None:
            previous = stamp
        valid.append({"open": o, "high": h, "low": low, "close": c, "timestamp": stamp})
    return valid


def analyze_binary_options(
    candles: list[dict[str, Any]],
    symbol: str,
    interval: str = "1m",
    higher_timeframes: dict[str, list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    """Explainable closed-candle CALL/PUT research signal; score is not a win probability."""
    bars = _valid_candles(candles)
    if len(bars) < 60:
        return {
            "symbol": symbol, "decision": "NO_TRADE", "score": 0, "confidence": 0,
            "status": "insufficient_data", "candles_used": len(bars),
            "rationale": ["يلزم 60 شمعة صحيحة على الأقل قبل إصدار إشارة."],
            "execution_enabled": False, "engine_version": "1.0.0",
        }

    closes = [x["close"] for x in bars]
    highs = [x["high"] for x in bars]
    lows = [x["low"] for x in bars]
    opens = [x["open"] for x in bars]
    fast, slow, trend = _ema(closes, 9), _ema(closes, 21), _ema(closes, 50)
    rsi = _rsi(closes)
    macd_line = [a - b for a, b in zip(_ema(closes, 12), _ema(closes, 26))]
    macd_signal = _ema(macd_line, 9)
    hist = macd_line[-1] - macd_signal[-1] if macd_signal else 0.0
    adx = _adx(bars)
    tr_values = []
    for i in range(1, len(bars)):
        tr_values.append(max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1])))
    atr = sum(tr_values[-14:]) / min(14, len(tr_values))
    avg_range = sum((h-l) for h,l in zip(highs[-20:], lows[-20:])) / 20
    candle = bars[-1]
    body = abs(candle["close"] - candle["open"])
    candle_range = max(candle["high"] - candle["low"], 1e-12)
    body_ratio = body / candle_range
    recent_high, recent_low = max(highs[-20:-1]), min(lows[-20:-1])
    momentum = closes[-1] - closes[-4]
    long_votes = short_votes = 0
    rationale: list[str] = []

    def vote(condition: bool, points: int, reason: str, bullish: bool = True):
        nonlocal long_votes, short_votes
        if condition:
            if bullish:
                long_votes += points
            else:
                short_votes += points
            rationale.append(reason)

    vote(fast[-1] > slow[-1] > trend[-1], 22, "ترتيب EMA 9/21/50 صاعد.")
    vote(fast[-1] < slow[-1] < trend[-1], 22, "ترتيب EMA 9/21/50 هابط.", False)
    vote(hist > 0 and macd_line[-1] > macd_line[-2], 14, "زخم MACD يتحسن صعوداً.")
    vote(hist < 0 and macd_line[-1] < macd_line[-2], 14, "زخم MACD يتراجع هبوطاً.", False)
    vote(rsi is not None and 52 <= rsi <= 68, 12, f"RSI متوازن لصالح الصعود ({rsi:.1f}).")
    vote(rsi is not None and 32 <= rsi <= 48, 12, f"RSI متوازن لصالح الهبوط ({rsi:.1f}).", False)
    vote(momentum > 0 and candle["close"] > candle["open"], 10, "الزخم والشمعة الأخيرة إيجابيان.")
    vote(momentum < 0 and candle["close"] < candle["open"], 10, "الزخم والشمعة الأخيرة سلبيان.", False)
    vote(candle["close"] > recent_high, 12, "اختراق قمة آخر 19 شمعة بإغلاق.")
    vote(candle["close"] < recent_low, 12, "كسر قاع آخر 19 شمعة بإغلاق.", False)
    if adx is not None and adx >= 20:
        rationale.append(f"قوة الاتجاه ADX={adx:.1f} تدعم وجود اتجاه.")
    elif adx is not None:
        rationale.append(f"ADX={adx:.1f}: الاتجاه ضعيف؛ الحذر من التذبذب.")
    else:
        rationale.append("ADX غير متاح بعد.")

    mtf = {}
    for tf, rows in (higher_timeframes or {}).items():
        higher = _valid_candles(rows)
        if len(higher) >= 55:
            hclose = [x["close"] for x in higher]
            e21, e50 = _ema(hclose, 21)[-1], _ema(hclose, 50)[-1]
            mtf[tf] = "BULLISH" if e21 > e50 else "BEARISH" if e21 < e50 else "NEUTRAL"
    bullish_mtf = sum(v == "BULLISH" for v in mtf.values())
    bearish_mtf = sum(v == "BEARISH" for v in mtf.values())
    if mtf:
        if bullish_mtf == len(mtf):
            long_votes += 12
            rationale.append("الأطر الزمنية الأعلى متوافقة صعوداً.")
        elif bearish_mtf == len(mtf):
            short_votes += 12
            rationale.append("الأطر الزمنية الأعلى متوافقة هبوطاً.")
        elif bullish_mtf and bearish_mtf:
            rationale.append("الأطر الزمنية متعارضة؛ تم تخفيض الثقة.")

    max_score = 92 if mtf else 80
    long_score = min(100, round(long_votes / max_score * 100))
    short_score = min(100, round(short_votes / max_score * 100))
    difference = abs(long_score - short_score)
    chosen = "CALL" if long_score > short_score else "PUT" if short_score > long_score else "NO_TRADE"
    score = max(long_score, short_score)
    blockers = []
    if adx is not None and adx < 12:
        blockers.append("سوق جانبي شديد الضعف.")
    if avg_range <= 0 or atr / max(closes[-1], 1e-12) > 0.004:
        blockers.append("تذبذب مرتفع أو بيانات نطاق غير مستقرة.")
    if body_ratio < 0.18:
        blockers.append("شمعة الإغلاق ضعيفة الجسم.")
    if difference < 18:
        blockers.append("لا يوجد تفوق واضح بين CALL و PUT.")
    if score < 68:
        blockers.append("قوة التوافق أقل من عتبة الإشارة 68/100.")
    if mtf and not ((chosen == "CALL" and bullish_mtf == len(mtf)) or (chosen == "PUT" and bearish_mtf == len(mtf))):
        blockers.append("تأكيد الأطر الأعلى غير مكتمل.")
    decision = chosen if not blockers else "NO_TRADE"
    if blockers:
        rationale.extend(blockers)
    return {
        "symbol": symbol, "provider": "deriv", "interval": interval,
        "decision": decision, "candidate": chosen,
        "score": score, "long_score": long_score, "short_score": short_score,
        "confidence": round(score / 100, 2),
        "score_is_probability": False,
        "status": "signal_candidate" if decision != "NO_TRADE" else "wait",
        "candles_used": len(bars), "latest_closed_candle": candle.get("timestamp"),
        "indicators": {
            "ema9": round(fast[-1], 8), "ema21": round(slow[-1], 8),
            "ema50": round(trend[-1], 8), "rsi14": round(rsi, 2) if rsi is not None else None,
            "macd_histogram": round(hist, 10), "adx14": round(adx, 2) if adx is not None else None,
            "atr14": round(atr, 10), "last_candle_body_ratio": round(body_ratio, 3),
        },
        "higher_timeframes": mtf, "rationale": rationale,
        "blockers": blockers,
        "expiry_guidance": {"1m": 60, "5m": 300, "15m": 900}.get(interval, 60),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "execution_enabled": False, "engine_version": "1.0.0",
        "disclaimer": "درجة التوافق ليست احتمال ربح؛ لا تُستخدم إشارة قبل اختبار تاريخي وخارج العينة واختبار أمامي.",
    }
