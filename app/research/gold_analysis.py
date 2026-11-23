"""Explainable, read-only multi-timeframe XAUUSD technical analysis."""
from __future__ import annotations

from datetime import datetime, timezone
from math import isfinite


TIMEFRAME_SECONDS = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600}


def _number(row, key):
    value = float(row[key])
    if not isfinite(value):
        raise ValueError("Non-finite candle value")
    return value


def _ema(values, period):
    if len(values) < period:
        return None
    alpha = 2.0 / (period + 1)
    current = sum(values[:period]) / period
    for value in values[period:]:
        current = alpha * value + (1 - alpha) * current
    return current


def _rsi(values, period=14):
    if len(values) <= period:
        return None
    changes = [values[i] - values[i - 1] for i in range(1, len(values))]
    gains = [max(x, 0.0) for x in changes]
    losses = [max(-x, 0.0) for x in changes]
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for gain, loss in zip(gains[period:], losses[period:]):
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else 50.0
    return 100 - (100 / (1 + avg_gain / avg_loss))


def _atr(rows, period=14):
    if len(rows) <= period:
        return None
    tr = []
    for i, row in enumerate(rows):
        high, low, close = _number(row, "high"), _number(row, "low"), _number(row, "close")
        prev_close = _number(rows[i - 1], "close") if i else close
        tr.append(max(high - low, abs(high - prev_close), abs(low - prev_close)))
    value = sum(tr[1:period + 1]) / period
    for item in tr[period + 1:]:
        value = (value * (period - 1) + item) / period
    return value


def _time(row):
    raw = row.get("epoch") or row.get("time")
    if raw:
        try:
            return datetime.fromtimestamp(float(raw), timezone.utc)
        except (TypeError, ValueError, OSError):
            pass
    raw = row.get("openTime") or row.get("timestamp")
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def _closed(rows, timeframe, now):
    seconds = TIMEFRAME_SECONDS[timeframe]
    clean = []
    seen = set()
    for row in rows:
        try:
            o, h, low, c = (_number(row, k) for k in ("open", "high", "low", "close"))
            stamp = _time(row)
            if stamp is None or h < max(o, low, c) or low > min(o, h, c):
                continue
            epoch = int(stamp.timestamp())
            bucket = epoch - epoch % seconds
            if bucket in seen or bucket + seconds > now.timestamp():
                continue
            seen.add(bucket)
            clean.append({**row, "open": o, "high": h, "low": low, "close": c, "_bucket": bucket})
        except (KeyError, TypeError, ValueError):
            continue
    return sorted(clean, key=lambda x: x["_bucket"])


def _timeframe_view(rows):
    closes = [x["close"] for x in rows]
    e20, e50, e200 = _ema(closes, 20), _ema(closes, 50), _ema(closes, 200)
    last = closes[-1]
    rsi = _rsi(closes)
    if e20 is None or e50 is None:
        trend = "insufficient"
    elif last > e20 > e50 and (e200 is None or e50 > e200):
        trend = "bullish"
    elif last < e20 < e50 and (e200 is None or e50 < e200):
        trend = "bearish"
    else:
        trend = "neutral"
    return {"trend": trend, "close": last, "ema20": e20, "ema50": e50,
            "ema200": e200, "rsi14": round(rsi, 2) if rsi is not None else None}


def analyze_gold(candles_by_tf: dict, quote: dict | None = None, now: datetime | None = None):
    """Return a conservative confluence decision; score is not win probability."""
    now = now or datetime.now(timezone.utc)
    cleaned = {tf: _closed(candles_by_tf.get(tf, []), tf, now) for tf in TIMEFRAME_SECONDS}
    minimum = {"1m": 60, "5m": 60, "15m": 60, "1h": 55}
    missing = [tf for tf, count in minimum.items() if len(cleaned[tf]) < count]
    if missing:
        return {"status": "insufficient_data", "decision": "WAIT", "score": 0,
                "score_label": "درجة توافق فني وليست احتمال ربح",
                "reasons": [f"بيانات شموع مغلقة غير كافية: {', '.join(missing)}"],
                "timeframes": {tf: {"bars": len(cleaned[tf])} for tf in TIMEFRAME_SECONDS},
                "execution_enabled": False}

    views = {tf: _timeframe_view(rows) for tf, rows in cleaned.items()}
    m1, m5, m15, h1 = (views[x] for x in ("1m", "5m", "15m", "1h"))
    atr = _atr(cleaned["5m"])
    close = m5["close"]
    if not atr or atr <= 0:
        return {"status": "invalid_volatility", "decision": "WAIT", "score": 0,
                "reasons": ["تعذر حساب ATR بشكل موثوق"], "timeframes": views,
                "execution_enabled": False}

    bull = sum(v["trend"] == "bullish" for v in (m1, m5, m15, h1))
    bear = sum(v["trend"] == "bearish" for v in (m1, m5, m15, h1))
    direction = "CALL" if bull >= 3 and h1["trend"] == "bullish" and m15["trend"] == "bullish" else (
        "PUT" if bear >= 3 and h1["trend"] == "bearish" and m15["trend"] == "bearish" else "WAIT"
    )
    reasons = []
    score = 0
    if direction != "WAIT":
        score += 35
        reasons.append("اتجاه الإطارين 1H و15M متوافق مع أغلبية الأطر")
    else:
        reasons.append("الأطر الزمنية غير متوافقة بما يكفي؛ لا توجد إشارة اتجاهية")
    rsi = m5["rsi14"]
    if direction == "CALL":
        if rsi is not None and 50 <= rsi <= 68:
            score += 15; reasons.append("RSI على 5M يدعم الصعود دون تشبع واضح")
        elif rsi is not None and rsi > 75:
            score -= 12; reasons.append("RSI مرتفع: خطر مطاردة حركة صاعدة ممتدة")
        else:
            reasons.append("RSI لا يقدم تأكيداً صاعداً قوياً")
    elif direction == "PUT":
        if rsi is not None and 32 <= rsi <= 50:
            score += 15; reasons.append("RSI على 5M يدعم الهبوط دون تشبع واضح")
        elif rsi is not None and rsi < 25:
            score -= 12; reasons.append("RSI منخفض جداً: خطر مطاردة حركة هابطة ممتدة")
        else:
            reasons.append("RSI لا يقدم تأكيداً هابطاً قوياً")

    last = cleaned["5m"][-1]
    prev = cleaned["5m"][-2]
    candle_range = last["high"] - last["low"]
    body = abs(last["close"] - last["open"])
    if direction == "CALL" and last["close"] > last["open"] and last["close"] > prev["high"]:
        score += 20; reasons.append("شمعة 5M مغلقة صاعدة واخترقت قمة الشمعة السابقة")
    elif direction == "PUT" and last["close"] < last["open"] and last["close"] < prev["low"]:
        score += 20; reasons.append("شمعة 5M مغلقة هابطة وكسرت قاع الشمعة السابقة")
    elif direction != "WAIT":
        reasons.append("لا يوجد تأكيد اختراق من شمعة 5M المغلقة")

    if candle_range > 2.2 * atr or body > 1.8 * atr:
        score -= 18
        reasons.append("حركة 5M واسعة مقارنة بـ ATR؛ احتمال دخول متأخر وتقلب مرتفع")
    else:
        score += 10
        reasons.append("تقلب 5M ضمن نطاق ATR المعتاد")

    # Recent swing levels, excluding the latest candle to avoid look-ahead.
    recent = cleaned["5m"][-21:-1]
    resistance = max(x["high"] for x in recent)
    support = min(x["low"] for x in recent)
    if direction == "CALL" and resistance - close < 0.35 * atr:
        score -= 12; reasons.append("السعر قريب جداً من مقاومة محلية")
    elif direction == "PUT" and close - support < 0.35 * atr:
        score -= 12; reasons.append("السعر قريب جداً من دعم محلي")

    q_age = (quote or {}).get("age_seconds")
    q_price = (quote or {}).get("price")
    if q_age is None or q_age > 15 or q_price is None:
        direction = "WAIT"; score = 0
        reasons.append("سعر Deriv اللحظي قديم أو غير متاح؛ تم إيقاف الإشارة")
    elif abs(float(q_price) - close) > 1.5 * atr:
        direction = "WAIT"; score = 0
        reasons.append("فرق السعر اللحظي عن آخر إغلاق 5M أكبر من 1.5 ATR؛ تحقق من اتساق البيانات")

    score = max(0, min(100, int(round(score))))
    decision = direction if direction != "WAIT" and score >= 70 else "WAIT"
    if decision == "WAIT" and direction != "WAIT":
        reasons.append("التوافق أقل من عتبة 70/100؛ انتظر ولا تدخل")
    entry = stop = target1 = target2 = None
    if decision in ("CALL", "PUT"):
        entry = float(q_price)
        if decision == "CALL":
            stop, target1, target2 = entry - 1.25 * atr, entry + 1.5 * atr, entry + 2.2 * atr
        else:
            stop, target1, target2 = entry + 1.25 * atr, entry - 1.5 * atr, entry - 2.2 * atr

    return {
        "status": "ready", "provider": "deriv", "symbol": (quote or {}).get("symbol", "XAUUSD"),
        "decision": decision, "directional_candidate": direction, "score": score,
        "score_label": "درجة توافق فني وليست احتمال ربح",
        "timeframes": {tf: {**views[tf], "closed_bars": len(cleaned[tf])} for tf in TIMEFRAME_SECONDS},
        "rsi14_5m": rsi, "atr14_5m": round(atr, 5),
        "levels": {"support": round(support, 5), "resistance": round(resistance, 5)},
        "trade_plan": {"entry_reference": round(entry, 5) if entry is not None else None,
                       "stop_loss": round(stop, 5) if stop is not None else None,
                       "take_profit_1": round(target1, 5) if target1 is not None else None,
                       "take_profit_2": round(target2, 5) if target2 is not None else None,
                       "risk_reward_target_1": 1.2 if entry is not None else None,
                       "note": "مستويات تعليمية محسوبة من ATR؛ ليست أمراً ولا ضماناً للسعر"},
        "reasons": reasons, "analyzed_at": now.isoformat(),
        "data_quality": {"quote_age_seconds": q_age, "closed_bars": {tf: len(v) for tf, v in cleaned.items()}},
        "execution_enabled": False,
        "disclaimer": "تحليل فني احتمالي للبحث فقط؛ لا توجد نسبة نجاح مضمونة ولا تنفيذ صفقات."
    }
