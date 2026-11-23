"""Deriv-backed, read-only XAU/USD Forex market data and live tick stream."""
import json
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.feeds.deriv import DerivFeed

router = APIRouter(prefix="/forex/gold", tags=["forex-gold"])
GOLD_SYMBOL_PREFERENCE = ("frxXAUUSD",)


async def resolve_gold_symbol(feed: DerivFeed | None = None) -> dict:
    """Resolve Gold/USD from Deriv's live active-symbol catalogue; never guess availability."""
    provider = feed or DerivFeed()
    try:
        symbols = await provider.symbols()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Deriv symbol catalogue unavailable: {exc}") from exc

    normalized = []
    for item in symbols:
        code = str(item.get("symbol") or "").strip()
        name = str(item.get("display_name") or item.get("name") or "").strip()
        haystack = f"{code} {name}".lower()
        if code.lower() in {s.lower() for s in GOLD_SYMBOL_PREFERENCE} or (
            "gold" in haystack and ("usd" in haystack or "xau" in haystack)
        ):
            normalized.append(item)

    for preferred in GOLD_SYMBOL_PREFERENCE:
        for item in normalized:
            if str(item.get("symbol", "")).lower() == preferred.lower():
                return item
    if normalized:
        return normalized[0]
    raise HTTPException(
        status_code=503,
        detail="Deriv does not currently list an active Gold/USD (XAUUSD) symbol. No substitute asset was selected.",
    )


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
