import os
from fastapi import FastAPI, HTTPException, Query
from app.feeds.service import MarketDataService
from app.feeds.normalization import align_candles, classify_market
from app.models import SignalDecision

app = FastAPI(
    title="BinaryAI-Trader API",
    version="0.3.0",
    description="Free-first, read-only market-data research API. No live execution.",
)


def data_service():
    # BiQuote is the default reference adapter. OTCharts is optional and never
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
            "provider": "biquote",
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
            "provider": "biquote",
            "symbol": symbol.upper(),
            "market_kind": classify_market(symbol),
            "candles": candles,
        }
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Reference candle error: {exc}") from exc


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


@app.get("/signals/example", response_model=SignalDecision)
async def example_signal():
    return SignalDecision(
        symbol="EURUSD",
        decision="NO_TRADE",
        confidence=0.0,
        rationale=["No strategy has passed historical and forward validation. Data availability alone is not a trading edge."],
    )
