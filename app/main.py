from fastapi import FastAPI

from app.models import SignalDecision

app = FastAPI(
    title="BinaryAI-Trader API",
    version="0.1.0",
    description="Independent market-data quality and binary-options research API.",
)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "BinaryAI-Trader", "mode": "research_only"}


@app.get("/providers")
async def providers():
    return {
        "active_provider": "disabled",
        "providers": {
            "quotex": {
                "enabled": False,
                "status": "unavailable",
                "reason": "No verified authorized public data API configured",
            },
            "independent_market_data": {
                "enabled": False,
                "status": "awaiting_configuration",
            },
        },
    }


@app.get("/signals/example", response_model=SignalDecision)
async def example_signal():
    return SignalDecision(
        symbol="EURUSD",
        decision="NO_TRADE",
        confidence=0.0,
        rationale=["No live feed or validated strategy is configured."],
    )
