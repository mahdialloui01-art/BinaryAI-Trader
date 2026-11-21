# BinaryAI-Trader

Independent binary-options research and signal-analysis platform. This repository is separate from GoldAI Trader.

## Free-first policy
- The primary feed is Deriv's public, read-only WebSocket market-data endpoint; no account token or API key is needed for public symbols, ticks, and historical candles.
- Deriv prices are Deriv prices, not Quotex OTC prices and not a guarantee of matching any other broker.
- The adapter exposes the active-symbol catalogue, tick streaming, OHLC history, and available contract types for an underlying symbol.
- No trade execution, account login, proposal purchase, or live order is enabled. The app remains analysis-only.
- Store/replay historical data where permitted to reduce repeated requests.

## Current scope
- Normalized live-tick and OHLC data adapters.
- Provider health and symbol-catalogue endpoints.
- Conservative OTC symbol classification.
- UTC timestamp alignment and candle comparison diagnostics.
- Professional multi-factor binary-options research engine: EMA trend structure, swing/BOS market structure, liquidity sweeps, FVG, candle rejection/engulfing patterns, MACD/RSI/ADX/DI, ATR/Bollinger volatility regime and two higher-timeframe confirmations.
- Closed-candle and timestamp-quality gates; stale, gapped, conflicting or weak setups fail closed to NO_TRADE.
- Walk-forward replay using close-time decisions, next-candle OPEN entries and expiry CLOSE settlements, with chronological train/validation/test reports.
- Local SQLite historical candle cache with upsert/deduplication.
- Collection and replay endpoints for stored reference candles.
- Expiry-aware CALL/PUT backtest evaluator with tie handling, payout P&L, losing streaks, drawdown and chronological splits.

## Important integration limits
Deriv's public market-data WebSocket is unauthenticated and read-only. It does not grant access to account-scoped trading actions. This project will not request account tokens or place trades. Deriv synthetic indices are generated instruments and must not be described as Quotex OTC or real-market Forex.

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
- `GET /symbols` — Deriv active-symbol catalogue.
- `GET /market/{symbol}/tick` — latest Deriv tick.
- `GET /market/{symbol}/candles?interval=1m&limit=300` — Deriv OHLC history.
- `GET /market/{symbol}/quality?interval=1m&limit=100` — tick/candle age, timestamp gaps, duplicates and OHLC integrity diagnostics.
- `GET /deriv/{symbol}/contracts` — contract types Deriv lists for the selected underlying.
- `GET /deriv/stream?symbol=frxEURUSD` — public live tick stream as server-sent events.
- `GET /quotex/{symbol}/candles` — optional OTCharts read-only candles.
- `GET /compare/{symbol}/candles` — timestamp-aligned diagnostics when OTCharts is configured.
- `POST /collect/{symbol}/candles?interval=1m&limit=300` — fetch and store a candle batch.
- `GET /history/{symbol}/candles?provider=deriv&interval=1m` — replay locally stored candles.
- `GET /history/stats` — local cache counts.
- `POST /research/evaluate` — evaluate supplied historical CALL/PUT entries against OHLC candles; returns win/loss/tie counts, payout-adjusted P&L, expectancy, losing streak, drawdown and train/validation/test summaries.
- `GET /analysis/{symbol}?interval=1m&limit=250` — explainable multi-factor CALL/PUT/NO_TRADE analysis with module scores, blockers, structure, liquidity and higher-timeframe state.
- `GET /research/walk-forward/{symbol}?interval=1m&limit=1500&payout=0.8&expiry_bars=1` — replays the production signal rules without lookahead, then reports payout-adjusted results and chronological splits.
- `GET /signals/example` — static NO_TRADE placeholder; not the production analysis endpoint.

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
The evaluator measures entries supplied by the caller; it does **not** create signals or prove a strategy has an edge. The walk-forward endpoint generates signals from historical data using only candles available at each decision time, enters on the next candle OPEN, and settles at the configured expiry candle CLOSE. It reports sample-size warnings; a positive backtest is not proof of a live edge. The chronological split is based on candle index, and forward validation still requires genuinely unseen data.

## Android client
The Android client includes a dashboard, selectable Deriv binary-options underlyings, 1-minute chart, live reference-price stream, feed-quality diagnostics, history cache controls, a detailed professional analysis report, and a walk-forward validation report. The app requires the HTTPS URL of a deployed BinaryAI API.

## Validation roadmap
1. Verify API payloads against live provider responses.
2. Test stale-feed rejection and candle timestamp conventions.
3. Expand the SQLite store with retention/export and verify persistence on the chosen host.
4. Evaluate strategies with chronological train/test splits, costs, expiry labels and forward tests.
5. Release an Android client only after the backend and strategy have measurable validation.
