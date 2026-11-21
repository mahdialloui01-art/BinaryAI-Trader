import os
from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import StreamingResponse
import httpx
import re
from app.feeds.service import MarketDataService
from app.feeds.normalization import align_candles, candle_timestamp, classify_market, parse_timestamp
from app.models import SignalDecision
from app.storage import CandleStore

from pydantic import BaseModel, Field
from app.research.backtest import evaluate_binary_trades

class ResearchEvaluationRequest(BaseModel):
    candles: list[dict] = Field(min_length=2, max_length=20000)
    trades: list[dict] = Field(default_factory=list, max_length=10000)
    payout: float = Field(default=0.80, gt=0, le=1)
    stake: float = Field(default=1.0, gt=0)
    initial_equity: float = Field(default=100.0, gt=0)
    tie_rule: str = "refund"
    train_fraction: float = Field(default=0.60, gt=0, lt=1)
    validation_fraction: float = Field(default=0.20, gt=0, lt=1)

app = FastAPI(
    title="BinaryAI-Trader API",
    version="0.3.0",
    description="Free-first, read-only market-data research API. No live execution.",
)


@app.post("/research/evaluate")
async def research_evaluate(request: ResearchEvaluationRequest):
    try:
        return evaluate_binary_trades(
            request.candles, request.trades, request.payout, request.stake,
            request.initial_equity, request.tie_rule,
            request.train_fraction, request.validation_fraction,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


def data_service():
    # Deriv is the primary public reference adapter. OTCharts remains optional and never
    # required for the free-first core.
    return MarketDataService(os.getenv("OTCHARTS_API_KEY") or None)


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "BinaryAI-Trader",
        "mode": "research_only",
        "execution_enabled": False,
        "free_first": True,
        "feeds": await data_service().health(),
    }


@app.get("/providers")
async def providers():
    return await data_service().health()


@app.get("/symbols")
async def symbols():
    """Return the reference provider catalogue; availability is not guaranteed."""
    try:
        items = await data_service().reference_symbols()
        return {
            "provider": "deriv",
            "count": len(items),
            "symbols": [
                {**item, "market_kind": classify_market(str(item.get("symbol", item.get("name", ""))))}
                for item in items
            ],
            "note": "Catalogue membership does not mean the instrument is currently streaming.",
        }
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Symbol catalogue unavailable: {exc}") from exc


@app.get("/market/{symbol}/tick")
async def market_tick(symbol: str):
    try:
        return await data_service().reference_tick(symbol.upper())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Reference feed error: {exc}") from exc


@app.get("/market/{symbol}/candles")
async def market_candles(
    symbol: str,
    interval: str = Query(default="1m", pattern="^(1m|5m|15m|30m|1h|4h|1d)$"),
    limit: int = Query(default=300, ge=1, le=1000),
):
    try:
        candles = await data_service().reference_candles(symbol.upper(), interval, limit)
        return {
            "provider": "deriv",
            "symbol": symbol.upper(),
            "market_kind": classify_market(symbol),
            "candles": candles,
        }
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Reference candle error: {exc}") from exc


@app.get("/market/{symbol}/quality")
async def market_quality(
    symbol: str,
    interval: str = Query(default="1m", pattern="^(1m|5m|15m|30m|1h|4h|1d)$"),
    limit: int = Query(default=100, ge=10, le=500),
):
    """Read-only feed diagnostics: age, gaps, duplicates and OHLC integrity."""
    seconds = {"1m": 60, "5m": 300, "15m": 900, "30m": 1800,
               "1h": 3600, "4h": 14400, "1d": 86400}[interval]
    try:
        service = data_service()
        tick, candles = await __import__("asyncio").gather(
            service.reference_tick(symbol.upper()),
            service.reference_candles(symbol.upper(), interval, limit),
        )
        now = datetime.now(timezone.utc)
        tick_time = parse_timestamp(tick.get("timestamp"))
        tick_age = max(0.0, (now - tick_time).total_seconds()) if tick_time else None
        stamps = []
        invalid_ohlc = 0
        for candle in candles:
            stamp = candle_timestamp(candle)
            if stamp:
                stamps.append(stamp)
            try:
                o, h, low, c = (float(candle[k]) for k in ("open", "high", "low", "close"))
                if h < max(o, c, low) or low > min(o, c, h):
                    invalid_ohlc += 1
            except (KeyError, TypeError, ValueError):
                invalid_ohlc += 1
        unique = sorted(set(stamps))
        duplicate_count = len(stamps) - len(unique)
        gaps = 0
        if len(unique) > 1:
            for left, right in zip(unique, unique[1:]):
                delta = (right - left).total_seconds()
                if delta > seconds * 1.5:
                    gaps += max(1, round(delta / seconds) - 1)
        latest_age = max(0.0, (now - unique[-1]).total_seconds()) if unique else None
        tick_stale = tick_age is None or tick_age > max(30, seconds * 2)
        candle_stale = latest_age is None or latest_age > max(180, seconds * 2)
        flags = []
        if tick_stale: flags.append("TICK_STALE_OR_UNTIMED")
        if candle_stale: flags.append("CANDLE_STALE_OR_UNTIMED")
        if gaps: flags.append("CANDLE_GAPS")
        if duplicate_count: flags.append("DUPLICATE_TIMESTAMPS")
        if invalid_ohlc: flags.append("INVALID_OHLC")
        return {
            "provider": "deriv",
            "symbol": symbol.upper(),
            "interval": interval,
            "market_kind": classify_market(symbol),
            "checked_at": now.isoformat(),
            "tick_age_seconds": round(tick_age, 2) if tick_age is not None else None,
            "latest_candle_age_seconds": round(latest_age, 2) if latest_age is not None else None,
            "candles_received": len(candles),
            "timestamped_candles": len(stamps),
            "duplicate_timestamps": duplicate_count,
            "estimated_missing_bars": gaps,
            "invalid_ohlc_bars": invalid_ohlc,
            "status": "stale" if tick_stale or candle_stale else ("degraded" if flags else "healthy"),
            "flags": flags,
            "note": "Freshness is measured against UTC timestamps; a healthy reference feed is not proof of broker price parity.",
        }
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Feed quality check failed: {exc}") from exc


@app.get("/deriv/stream")
async def deriv_stream(symbol: str = Query(..., min_length=2, max_length=30, pattern="^[A-Za-z0-9_]+$")):
    """Stream public Deriv ticks as server-sent events; no account token required."""
    async def relay():
        try:
            yield "event: status\\ndata: " + __import__("json").dumps({"status":"connecting","provider":"deriv","symbol":symbol}) + "\\n\\n"
            async for tick in data_service().stream_reference_ticks(symbol):
                yield "event: tick\\ndata: " + __import__("json").dumps(tick) + "\\n\\n"
        except Exception as exc:
            yield "event: error\\ndata: " + __import__("json").dumps({"provider":"deriv","symbol":symbol,"error":str(exc)}) + "\\n\\n"
    return StreamingResponse(relay(), media_type="text/event-stream", headers={
        "Cache-Control":"no-cache, no-transform", "Connection":"keep-alive", "X-Accel-Buffering":"no"
    })


@app.get("/quotex/symbols")
async def quotex_symbols():
    """Return the exact live Quotex catalogue exposed by the optional provider."""
    service = data_service()
    if not service.quotex:
        raise HTTPException(status_code=503, detail="OTCharts is not configured; the free Deriv public market feed is separate.")
    try:
        return await service.quotex_symbols()
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=503, detail=f"OTCharts rejected the catalogue request (HTTP {exc.response.status_code}). Check key, selected book and plan.") from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"OTCharts catalogue unavailable: {exc}") from exc


@app.get("/quotex/stream")
async def quotex_stream(symbols: str = Query(..., min_length=1, max_length=1000)):
    """Proxy genuine OTCharts SSE ticks; the API key stays on the backend."""
    requested = [item.strip() for item in symbols.split(",") if item.strip()]
    if not requested or len(requested) > 50:
        raise HTTPException(status_code=400, detail="Provide between 1 and 50 comma-separated symbol IDs.")
    if any(not re.fullmatch(r"[A-Za-z0-9_#.-]{1,80}", item) for item in requested):
        raise HTTPException(status_code=400, detail="Invalid symbol ID; use exact IDs from /quotex/symbols.")
    service = data_service()
    if not service.quotex:
        raise HTTPException(status_code=503, detail="OTCharts is not configured; Deriv public market data is not Quotex OTC.")
    try:
        upstream_client, upstream_response = await service.open_quotex_stream(requested)
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        detail = "OTCharts refused the live stream. The free tier has no live streams; verify plan, venue access and stream allowance."
        if status == 401:
            detail = "OTCharts key is invalid, revoked or the account email is unconfirmed."
        elif status == 429:
            detail = "OTCharts stream/request limit reached; check the plan's stream allowance and retry-after."
        elif status == 502:
            detail = "OTCharts upstream venue is temporarily unavailable."
        raise HTTPException(status_code=503 if status in (401, 403, 429) else 502, detail=detail) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Could not open OTCharts live stream: {exc}") from exc

    async def relay():
        try:
            async for chunk in upstream_response.aiter_raw():
                if chunk:
                    yield chunk
        finally:
            await upstream_response.aclose()
            await upstream_client.aclose()

    return StreamingResponse(
        relay(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/quotex/{symbol}/candles")
async def quotex_candles(
    symbol: str,
    timeframe_seconds: int = Query(default=60, ge=1, le=86400),
    limit: int = Query(default=300, ge=1, le=5000),
):
    try:
        candles = await data_service().quotex_candles(symbol, timeframe_seconds, limit)
        return {
            "provider": "otcharts",
            "venue": "quotex",
            "symbol": symbol,
            "market_kind": classify_market(symbol, "quotex"),
            "candles": candles,
            "execution_enabled": False,
        }
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Optional OTCharts feed unavailable: {exc}") from exc


@app.get("/compare/{symbol}/candles")
async def compare_candles(
    symbol: str,
    interval: str = Query(default="1m", pattern="^(1m|5m|15m|30m|1h|4h|1d)$"),
    timeframe_seconds: int = Query(default=60, ge=1, le=86400),
    limit: int = Query(default=100, ge=1, le=500),
    tolerance: float = Query(default=0.0, ge=0.0),
):
    """Diagnostic comparison only; real-market and OTC feeds are not interchangeable."""
    service = data_service()
    if not service.quotex:
        raise HTTPException(status_code=503, detail="Optional OTCharts key not configured; free reference feed remains available.")
    try:
        reference, otc = await __import__("asyncio").gather(
            service.reference_candles(symbol.upper(), interval, limit),
            service.quotex_candles(symbol, timeframe_seconds, limit),
        )
        return {
            "symbol": symbol,
            "reference_market_kind": classify_market(symbol),
            "otcharts_market_kind": classify_market(symbol, "quotex"),
            "comparison": align_candles(reference, otc, tolerance),
            "interpretation": "Do not treat this comparison as price parity unless both feeds represent the same venue, instrument and candle convention.",
        }
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Feed comparison failed: {exc}") from exc


@app.post("/collect/{symbol}/candles")
async def collect_candles(
    symbol: str,
    interval: str = Query(default="1m", pattern="^(1m|5m|15m|30m|1h|4h|1d)$"),
    limit: int = Query(default=300, ge=1, le=1000),
):
    """Fetch from the free-first reference feed and persist a local historical batch."""
    try:
        candles = await data_service().reference_candles(symbol.upper(), interval, limit)
        result = CandleStore().upsert("deriv", symbol.upper(), interval, candles)
        return {
            "provider": "biquote",
            "symbol": symbol.upper(),
            "interval": interval,
            "received": len(candles),
            **result,
            "database_total": CandleStore().count("deriv"),
            "note": "Local SQLite cache; on ephemeral hosting it resets on redeploy unless a persistent disk is attached.",
        }
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Collection failed: {exc}") from exc


@app.get("/history/{symbol}/candles")
async def historical_candles(
    symbol: str,
    provider: str = Query(default="deriv", pattern="^(deriv|biquote|otcharts)$"),
    interval: str = Query(default="1m", pattern="^(1m|5m|15m|30m|1h|4h|1d)$"),
    limit: int = Query(default=500, ge=1, le=10000),
    since: str | None = Query(default=None),
):
    try:
        store = CandleStore()
        candles = store.get(provider, symbol.upper(), interval, limit, since)
        return {
            "provider": provider,
            "symbol": symbol.upper(),
            "interval": interval,
            "count": len(candles),
            "candles": candles,
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"History read failed: {exc}") from exc


@app.get("/history/stats")
async def history_stats():
    store = CandleStore()
    return {"stored_candles": store.count(), "deriv_candles": store.count("deriv"), "legacy_biquote_candles": store.count("biquote")}


@app.get("/signals/example", response_model=SignalDecision)
async def example_signal():
    return SignalDecision(
        symbol="EURUSD",
        decision="NO_TRADE",
        confidence=0.0,
        rationale=["No strategy has passed historical and forward validation. Data availability alone is not a trading edge."],
    )
