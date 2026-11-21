from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

OTC_MARKERS = ("_otc", "-otc", " otc")


def classify_market(symbol: str, venue: str | None = None) -> str:
    """Conservative classification: explicit OTC markers only."""
    text = f"{symbol} {venue or ''}".lower()
    if any(marker in text for marker in OTC_MARKERS) or " otc" in text:
        return "otc"
    if venue and venue.lower() in {"quotex_otc", "otc"}:
        return "otc"
    return "unknown"


def parse_timestamp(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        # Accept seconds or milliseconds since epoch.
        stamp = value / 1000 if value > 10_000_000_000 else value
        return datetime.fromtimestamp(stamp, tz=timezone.utc)
    if isinstance(value, str):
        normalized = value.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            return None
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)
    return None


def align_candles(left: list[dict], right: list[dict], tolerance: float = 0.0) -> dict:
    """Compare only candles with matching UTC open-time; never compare unmatched bars."""
    def index(rows):
        output = {}
        for row in rows:
            stamp = parse_timestamp(row.get("timestamp", row.get("time", row.get("time_utc"))))
            if stamp is not None:
                output[stamp.isoformat()] = row
        return output

    a, b = index(left), index(right)
    shared = sorted(set(a) & set(b))
    fields = ("open", "high", "low", "close")
    comparisons = []
    for key in shared:
        diffs = {}
        valid = True
        for field in fields:
            try:
                diffs[field] = abs(float(a[key][field]) - float(b[key][field]))
            except (KeyError, TypeError, ValueError):
                valid = False
        comparisons.append({
            "timestamp": key,
            "valid_ohlc_pair": valid,
            "differences": diffs,
            "within_tolerance": valid and all(value <= tolerance for value in diffs.values()),
        })
    return {
        "matched_candles": len(shared),
        "left_unmatched": len(set(a) - set(b)),
        "right_unmatched": len(set(b) - set(a)),
        "tolerance": tolerance,
        "comparisons": comparisons,
        "warning": "Different venues/providers may legitimately quote different prices; this is a diagnostic, not proof of feed equivalence.",
    }
