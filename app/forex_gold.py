"""Deriv-backed, read-only XAU/USD Forex market data and live tick stream."""
import asyncio
import json
import time
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.feeds.deriv import DerivFeed
from app.research.gold_analysis import analyze_gold

router = APIRouter(prefix="/forex/gold", tags=["forex-gold"])
GOLD_SYMBOL_PREFERENCE = ("frxXAUUSD",)
_GOLD_ANALYSIS_CACHE = {"created": 0.0, "result": None}
_GOLD_ANALYSIS_LOCK = asyncio.Lock()
_GOLD_ANALYSIS_CACHE_SECONDS = 8.0


async def resolve_gold_symbol(feed: DerivFeed | None = None) -> dict:
    """Return the explicitly configured Deriv XAUUSD underlying without a catalogue call.

    The app's live Gold quote/candle feed already identifies frxXAUUSD. Re-querying
    active_symbols before every Gold operation creates needless WebSocket handshakes
    and can rate-limit the analysis endpoint (HTTP 429). If this underlying is not
    available, the quote/history request itself will fail closed with a clear error.
    """
    return {
        "symbol": "frxXAUUSD",
        "name": "Gold / USD",
        "display_name": "Gold / USD",
        "market": "commodities",
        "exchange_is_open": None,
        "is_trading_suspended": False,
        "provider": "deriv",
        "symbol_source": "configured_deriv_underlying",
    }


def _age_seconds(timestamp: str | None) -> float | None:
    if not timestamp:
        return None
    try:
        stamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        return max(0.0, (datetime.now(timezone.utc) - stamp).total_seconds())
    except (TypeError, ValueError):
        return None


@router.get("/symbol")
async def gold_symbol():
    item = await resolve_gold_symbol()
    return {
        "provider": "deriv",
        "symbol": item.get("symbol"),
        "name": item.get("display_name") or item.get("name") or "Gold / USD",
        "market": item.get("market"),
        "exchange_is_open": item.get("exchange_is_open", False),
        "is_trading_suspended": item.get("is_trading_suspended", False),
        "execution_enabled": False,
    }


@router.get("/quote")
async def gold_quote():
    feed = DerivFeed()
    item = await resolve_gold_symbol(feed)
    try:
        tick = await feed.tick(item["symbol"])
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Deriv Gold tick unavailable: {exc}") from exc
    age = _age_seconds(tick.get("timestamp"))
    return {
        **tick,
        "name": item.get("display_name") or item.get("name") or "Gold / USD",
        "age_seconds": round(age, 2) if age is not None else None,
        "status": "live" if age is not None and age <= 15 else "stale",
        "execution_enabled": False,
        "note": "Live Deriv reference ticks; the quote is read-only and may differ from another broker's XAUUSD price.",
    }


@router.get("/candles")
async def gold_candles(
    interval: str = Query(default="1m", pattern="^(1m|5m|15m|30m|1h|4h|1d)$"),
    limit: int = Query(default=300, ge=10, le=1000),
):
    feed = DerivFeed()
    item = await resolve_gold_symbol(feed)
    try:
        rows = await feed.candles(item["symbol"], interval, limit)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Deriv Gold candle history unavailable: {exc}") from exc
    if not rows:
        raise HTTPException(status_code=503, detail="Deriv returned no Gold candles for this interval.")
    return {
        "provider": "deriv",
        "symbol": item["symbol"],
        "name": item.get("display_name") or item.get("name") or "Gold / USD",
        "interval": interval,
        "count": len(rows),
        "candles": rows,
        "execution_enabled": False,
    }


@router.get("/stream")
async def gold_stream():
    """Continuous Deriv tick stream for the currently active Gold/USD underlying."""
    feed = DerivFeed()
    item = await resolve_gold_symbol(feed)
    symbol = item["symbol"]

    async def relay():
        yield "retry: 3000\nevent: status\ndata: " + json.dumps({
            "status": "connected",
            "provider": "deriv",
            "symbol": symbol,
        }) + "\n\n"
        try:
            async for tick in feed.stream_ticks(symbol):
                yield "event: tick\ndata: " + json.dumps(tick, separators=(",", ":")) + "\n\n"
        except Exception as exc:
            yield "event: error\ndata: " + json.dumps({
                "provider": "deriv",
                "symbol": symbol,
                "error": str(exc),
            }) + "\n\n"

    return StreamingResponse(
        relay(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/analyze")
async def analyze_gold_market():
    """Conservative multi-timeframe Gold analysis from one Deriv WebSocket session."""
    feed = DerivFeed()
    item = await resolve_gold_symbol(feed)
    symbol = item["symbol"]

    # Coalesce simultaneous app refreshes and reuse a very recent snapshot.
    # This avoids opening repeated Deriv handshakes when the screen refreshes.
    async with _GOLD_ANALYSIS_LOCK:
        cache_age = time.monotonic() - _GOLD_ANALYSIS_CACHE["created"]
        if _GOLD_ANALYSIS_CACHE["result"] is not None and cache_age < _GOLD_ANALYSIS_CACHE_SECONDS:
            return {**_GOLD_ANALYSIS_CACHE["result"], "cache_age_seconds": round(cache_age, 2)}

        try:
            quote, candles = await feed.gold_analysis_snapshot(symbol)
        except Exception as exc:
            raise HTTPException(
                status_code=503,
                detail=f"Deriv Gold analysis temporarily rate-limited or unavailable: {exc}. Retry shortly; no stale signal was returned."
            ) from exc

        age = _age_seconds(quote.get("timestamp"))
        quote["age_seconds"] = age
        result = analyze_gold(candles, quote)
        result["name"] = item.get("display_name") or item.get("name") or "Gold / USD"
        result["live_price"] = quote.get("price")
        result["quote_timestamp"] = quote.get("timestamp")
        result["data_source_note"] = "Quote and five candle timeframes fetched over one Deriv WebSocket session."
        _GOLD_ANALYSIS_CACHE.update({"created": time.monotonic(), "result": result})
        return result
