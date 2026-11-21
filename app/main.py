import os
from fastapi import FastAPI, HTTPException, Query
from app.feeds.service import MarketDataService
from app.models import SignalDecision

app = FastAPI(title="BinaryAI-Trader API", version="0.2.0",
              description="Independent market-data quality and binary-options research API.")

def data_service():
    return MarketDataService(os.getenv("OTCHARTS_API_KEY") or None)

@app.get("/health")
async def health():
    return {"status": "ok", "service": "BinaryAI-Trader",
            "mode": "research_only", "feeds": await data_service().health()}

@app.get("/providers")
async def providers():
    return await data_service().health()

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
        return {"provider": "biquote", "symbol": symbol.upper(),
                "candles": await data_service().reference_candles(symbol.upper(), interval, limit)}
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
        return {"provider": "otcharts", "venue": "quotex", "symbol": symbol, "candles": candles}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Quotex-labelled feed unavailable: {exc}") from exc

@app.get("/signals/example", response_model=SignalDecision)
async def example_signal():
    return SignalDecision(
        symbol="EURUSD", decision="NO_TRADE", confidence=0.0,
        rationale=["No validated strategy is configured. Data availability alone is not a trading edge."],
    )
