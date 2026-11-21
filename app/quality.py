from datetime import datetime, timezone

from app.models import Candle, Tick


def age_seconds(timestamp: datetime, now: datetime | None = None) -> float:
    now = now or datetime.now(timezone.utc)
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return max(0.0, (now - timestamp).total_seconds())


def tick_is_fresh(tick: Tick, max_age_seconds: float = 10.0,
                  now: datetime | None = None) -> bool:
    return age_seconds(tick.timestamp, now) <= max_age_seconds


def candle_is_fresh(candle: Candle, max_age_seconds: float,
                    now: datetime | None = None) -> bool:
    return age_seconds(candle.timestamp, now) <= max_age_seconds


def compare_prices(price_a: float, price_b: float, tolerance: float) -> dict:
    """Compare two feeds without assuming either is the ground truth."""
    difference = abs(price_a - price_b)
    return {
        "price_a": price_a,
        "price_b": price_b,
        "absolute_difference": difference,
        "within_tolerance": difference <= tolerance,
    }


def compare_candles(a: Candle, b: Candle, tolerance: float) -> dict:
    same_identity = (
        a.symbol == b.symbol
        and a.market_kind == b.market_kind
        and a.timeframe_seconds == b.timeframe_seconds
        and a.timestamp == b.timestamp
    )
    fields = ("open", "high", "low", "close")
    diffs = {field: abs(getattr(a, field) - getattr(b, field)) for field in fields}
    return {
        "same_candle_identity": same_identity,
        "differences": diffs,
        "within_tolerance": same_identity and all(v <= tolerance for v in diffs.values()),
    }
