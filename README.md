# BinaryAI-Trader

Independent binary-options research and signal-analysis platform. This repository is separate from GoldAI Trader.

## Current scope
- Multi-provider market-data ingestion architecture.
- Normalized OHLC candles and live tick models.
- Feed health, freshness, duplicate and candle-consistency checks.
- Cross-provider price/candle comparison.
- Signal research only: CALL / PUT / NO_TRADE with an explicit expiry horizon.
- Historical and forward testing before any strategy is considered usable.

## Important integration limits
Quotex does not provide a generally documented public developer API for arbitrary third-party automated trading. This project will not use browser automation, reverse-engineered private endpoints, credential harvesting, or account-session scraping. The Quotex connector remains disabled until a documented, authorized data interface is available. A separate provider adapter can be enabled for independently licensed market data. OTC instruments must be identified and tested separately from real-market instruments.

This project does not place trades. Signals are research outputs, not guarantees of profit.

## Run locally
```bash
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Health: http://127.0.0.1:8000/health  
API docs: http://127.0.0.1:8000/docs

## Configuration
Copy `.env.example` to `.env`. No provider is enabled by default. Add credentials only for a provider whose terms authorize your intended use.

## Roadmap
1. Data contracts and validation.
2. Authorized live-data provider integration.
3. Historical data ingestion and replay.
4. Price/candle parity evaluation against the platform display.
5. Expiry-aware strategy research with out-of-sample and forward testing.
6. Android client and deployment after the backend is validated.
