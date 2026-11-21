# BinaryAI-Trader

Independent binary-options research and signal-analysis platform. This repository is separate from GoldAI Trader.

## Free-first policy
- The core uses the public, read-only BiQuote REST endpoints and does not require an API key according to its published interface.
- BiQuote is a reference feed, not a guaranteed mirror of Quotex or any broker. Current symbol coverage and streaming availability must be checked at runtime.
- OTCharts is an optional third-party read-only adapter. It requires its own key; free-tier limits and live-stream availability can change. The core does not depend on it.
- No paid data plan is enabled or assumed. A missing optional feed must never silently block the free reference feed.
- Store/replay historical data where permitted to reduce repeated requests.

## Current scope
- Normalized live-tick and OHLC data adapters.
- Provider health and symbol-catalogue endpoints.
- Conservative OTC symbol classification.
- UTC timestamp alignment and candle comparison diagnostics.
- Signal research only: CALL / PUT / NO_TRADE.
- Local SQLite historical candle cache with upsert/deduplication.
- Collection and replay endpoints for stored reference candles.
- Expiry-aware CALL/PUT backtest evaluator with tie handling, payout P&L, losing streaks, drawdown and chronological splits.

## Important integration limits
Quotex does not provide a generally documented public developer API for arbitrary third-party automated trading. This project will not use browser automation, reverse-engineered private endpoints, credential harvesting, or account-session scraping. OTCharts is independent of Quotex and is not an official Quotex API. OTC instruments must be identified and tested separately from real-market instruments.

This project does not place trades. Signals are research outputs, not guarantees of profit. Live execution remains disabled.

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

## Main endpoints
- `GET /health` — service and provider configuration (not a live feed probe).
- `GET /symbols` — BiQuote reference catalogue.
- `GET /market/{symbol}/tick` — reference tick.
- `GET /market/{symbol}/candles?interval=1m&limit=300` — reference OHLC.
- `GET /quotex/{symbol}/candles` — optional OTCharts read-only candles.
- `GET /compare/{symbol}/candles` — timestamp-aligned diagnostics when OTCharts is configured.
- `POST /collect/{symbol}/candles?interval=1m&limit=300` — fetch and store a candle batch.
- `GET /history/{symbol}/candles?provider=biquote&interval=1m` — replay locally stored candles.
- `GET /history/stats` — local cache counts.
- `POST /research/evaluate` — evaluate supplied historical CALL/PUT entries against OHLC candles; returns win/loss/tie counts, payout-adjusted P&L, expectancy, losing streak, drawdown and train/validation/test summaries.
- `GET /signals/example` — explicit NO_TRADE placeholder until a strategy passes validation.

### Research evaluator input
Send chronological candles and a separate list of explicit trade entries. `entry_index` identifies the candle whose OPEN is used as entry; `expiry_bars=1` settles at that candle's CLOSE. Example:
```json
{
  "candles": [
    {"timestamp":"2026-01-01T00:00:00Z","open":1.10,"high":1.12,"low":1.09,"close":1.11},
    {"timestamp":"2026-01-01T00:01:00Z","open":1.11,"high":1.13,"low":1.10,"close":1.12}
  ],
  "trades": [{"direction":"CALL","entry_index":0,"expiry_bars":1}],
  "payout": 0.80,
  "stake": 1.0,
  "tie_rule": "refund"
}
```
The evaluator measures entries supplied by the caller; it does **not** create signals or prove a strategy has an edge. The chronological split is based on candle index, and forward validation still requires genuinely unseen data.

## Validation roadmap
1. Verify API payloads against live provider responses.
2. Test stale-feed rejection and candle timestamp conventions.
3. Expand the SQLite store with retention/export and verify persistence on the chosen host.
4. Evaluate strategies with chronological train/test splits, costs, expiry labels and forward tests.
5. Release an Android client only after the backend and strategy have measurable validation.
