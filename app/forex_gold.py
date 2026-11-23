"""Read-only XAU/USD Forex reference data, isolated from Deriv Binary Options routes."""
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Query
import httpx

router = APIRouter(prefix="/forex/gold", tags=["forex-gold"])
YAHOO_SYMBOL = "XAUUSD=X"
YAHOO_CHART_URL = f"https://query1.finance.yahoo.com/v8/finance/chart/{YAHOO_SYMBOL}"
INTERVALS = {"1m": "1m", "5m": "5m", "15m": "15m", "30m": "30m", "1h": "60m", "1d": "1d"}
RANGES = {"1m": "1d", "5m": "5d", "15m": "1mo", "30m": "1mo", "1h": "3mo", "1d": "1y"}


async def _chart(interval: str) -> dict:
    params = {"range": RANGES[interval], "interval": INTERVALS[interval], "events": "div,splits"}
    headers = {"User-Agent": "Mozilla/5.0 (compatible; BinaryAI-Trader/2.5; read-only)"}
    try:
        async with httpx.AsyncClient(timeout=15.0, headers=headers) as client:
            response = await client.get(YAHOO_CHART_URL, params=params)
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(status_code=502, detail=f"Yahoo Finance gold feed unavailable: {exc}") from exc
    result = ((payload.get("chart") or {}).get("result") or [None])[0]
    error = (payload.get("chart") or {}).get("error")
    if not result:
        raise HTTPException(status_code=502, detail=f"Gold quote unavailable: {error or 'empty provider response'}")
    return result


def _rows(result: dict, limit: int) -> list[dict]:
    timestamps = result.get("timestamp") or []
    quote = (((result.get("indicators") or {}).get("quote") or [{}])[0])
    rows = []
    for i, stamp in enumerate(timestamps):
        try:
            values = {key: (quote.get(key) or [])[i] for key in ("open", "high", "low", "close", "volume")}
            if any(values[k] is None for k in ("open", "high", "low", "close")):
                continue
            rows.append({
                "timestamp": datetime.fromtimestamp(stamp, timezone.utc).isoformat(),
                "time_unix": stamp,
                **{k: float(v) if k != "volume" else (int(v) if v is not None else 0) for k, v in values.items()},
            })
        except (IndexError, TypeError, ValueError, OSError):
            continue
    return rows[-limit:]


@router.get("/quote")
async def gold_quote():
    result = await _chart("1m")
    rows = _rows(result, 5)
    meta = result.get("meta") or {}
    price = meta.get("regularMarketPrice")
    stamp = meta.get("regularMarketTime")
    if rows:
        price = rows[-1]["close"]
        stamp = rows[-1]["time_unix"]
    if price is None:
        raise HTTPException(status_code=502, detail="Gold provider returned no current price.")
    age = max(0, (datetime.now(timezone.utc).timestamp() - float(stamp))) if stamp else None
    return {
        "symbol": "XAUUSD", "name": "Gold / US Dollar", "price": float(price),
        "currency": meta.get("currency", "USD"), "provider": "Yahoo Finance chart (XAUUSD=X)",
        "timestamp": datetime.fromtimestamp(float(stamp), timezone.utc).isoformat() if stamp else None,
        "age_seconds": round(age, 1) if age is not None else None,
        "status": "stale" if age is None or age > 180 else "reference_feed",
        "execution_enabled": False,
        "note": "Read-only reference quote; Yahoo Finance may be delayed and is not guaranteed to match a broker's XAUUSD price.",
    }


@router.get("/candles")
async def gold_candles(
    interval: str = Query(default="1m", pattern="^(1m|5m|15m|30m|1h|1d)$"),
    limit: int = Query(default=300, ge=10, le=1000),
):
    result = await _chart(interval)
    rows = _rows(result, limit)
    if not rows:
        raise HTTPException(status_code=502, detail="Gold provider returned no valid OHLC candles.")
    return {
        "symbol": "XAUUSD", "interval": interval, "provider": "Yahoo Finance chart (XAUUSD=X)",
        "currency": (result.get("meta") or {}).get("currency", "USD"),
        "count": len(rows), "candles": rows, "execution_enabled": False,
        "note": "Reference candles only; timestamps are UTC and prices may be delayed versus your broker.",
    }
