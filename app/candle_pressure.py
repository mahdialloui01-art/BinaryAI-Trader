"""Per-candle buyer/seller pressure proxy for Deriv OHLC candles.

The score describes candle structure, not executed buyer/seller volume or a
probability of a successful binary-options contract.
"""
from __future__ import annotations

from math import isfinite


def _num(value, default=0.0):
    try:
        result = float(value)
        return result if isfinite(result) else default
    except (TypeError, ValueError):
        return default


def candle_pressure(candle: dict, *, live: bool = False) -> dict:
    o, h, low, close = (_num(candle.get(key)) for key in ("open", "high", "low", "close"))
    span = h - low
    if min(o, h, low, close) <= 0 or span <= 0 or h < max(o, close) or low > min(o, close):
        return {
            "status": "UNAVAILABLE_INVALID_OR_FLAT_CANDLE",
            "buyer_strength": None,
            "seller_strength": None,
            "dominant_side": "UNKNOWN",
            "score_type": "OHLC_PRESSURE_PROXY_NOT_TRADE_DELTA",
            "is_aggressor_delta": False,
            "live": bool(live),
        }

    close_location = min(1.0, max(0.0, (close - low) / span))
    body_direction = min(1.0, max(-1.0, (close - o) / span))
    upper_wick = max(0.0, h - max(o, close)) / span
    lower_wick = max(0.0, min(o, close) - low) / span
    structure_buy = (
        0.50 * close_location
        + 0.30 * ((body_direction + 1.0) / 2.0)
        + 0.20 * ((1.0 + lower_wick - upper_wick) / 2.0)
    )

    up = max(0, int(_num(candle.get("upTicks"))))
    down = max(0, int(_num(candle.get("downTicks"))))
    directional = up + down
    tick_proxy = up / directional if directional else None
    combined_buy = 0.70 * structure_buy + 0.30 * tick_proxy if live and tick_proxy is not None else structure_buy
    buyers = int(round(min(1.0, max(0.0, combined_buy)) * 100))
    sellers = 100 - buyers
    side = "BUYERS" if buyers >= 58 else "SELLERS" if sellers >= 58 else "BALANCED"
    difference = abs(buyers - sellers)
    quality = "STRONG" if difference >= 50 else "MODERATE" if difference >= 20 else "WEAK_OR_BALANCED"
    if live and directional < 5:
        quality = "LOW_SAMPLE"

    return {
        "status": "AVAILABLE",
        "buyer_strength": buyers,
        "seller_strength": sellers,
        "dominant_side": side,
        "pressure_strength": difference,
        "pressure_quality": quality,
        "close_location_percent": round(close_location * 100, 1),
        "body_percent_of_range": round(abs(close - o) / span * 100, 1),
        "upper_wick_percent": round(upper_wick * 100, 1),
        "lower_wick_percent": round(lower_wick * 100, 1),
        "tick_direction_proxy_percent": round((up - down) / directional * 100, 1) if directional else None,
        "tick_count": int(_num(candle.get("tickCount"))) if live else None,
        "score_type": "OHLC_AND_LIVE_TICK_DIRECTION_PROXY_NOT_TRADE_DELTA",
        "is_aggressor_delta": False,
        "live": bool(live),
    }


def candle_pressure_series(candles: list[dict]) -> list[dict]:
    results = []
    for candle in candles:
        is_live = bool(candle.get("isOpen", False))
        results.append({
            "timestamp": candle.get("timestamp") or candle.get("openTime") or candle.get("epoch"),
            **candle_pressure(candle, live=is_live),
        })
    return results
