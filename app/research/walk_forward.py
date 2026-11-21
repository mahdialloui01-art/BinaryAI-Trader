from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from app.research.backtest import evaluate_binary_trades
from app.research.engine import INTERVAL_SECONDS, _valid_candles, analyze_binary_options


def _stamp(row: dict[str, Any]) -> datetime | None:
    value = row.get("timestamp", row.get("time", row.get("openTime")))
    try:
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(value / 1000 if value > 10_000_000_000 else value, timezone.utc)
        if value is None:
            return None
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)
    except (ValueError, TypeError, OverflowError, OSError):
        return None


def walk_forward_binary_options(
    candles: list[dict[str, Any]],
    symbol: str,
    interval: str,
    higher_timeframes: dict[str, list[dict[str, Any]]],
    payout: float = 0.80,
    stake: float = 1.0,
    expiry_bars: int = 1,
    initial_equity: float = 100.0,
) -> dict[str, Any]:
    """Strict chronological replay: decide at candle close, enter next candle open, settle at expiry close."""
    if interval not in INTERVAL_SECONDS:
        raise ValueError("Unsupported interval")
    if expiry_bars not in (1, 2, 3):
        raise ValueError("expiry_bars must be 1, 2 or 3")
    if not 0 < payout <= 1 or stake <= 0 or initial_equity <= 0:
        raise ValueError("Invalid payout, stake or initial_equity")

    base = _valid_candles(candles)
    if len(base) < 180:
        raise ValueError("Walk-forward requires at least 180 valid chronological candles")
    stamps = [_stamp(x) for x in base]
    if any(x is None for x in stamps):
        raise ValueError("Every candle needs a valid timestamp for no-lookahead replay")
    if any(stamps[i] <= stamps[i - 1] for i in range(1, len(stamps))):
        raise ValueError("Candles must be strictly chronological")

    higher = {tf: _valid_candles(rows) for tf, rows in higher_timeframes.items()}
    higher_stamps = {tf: [_stamp(x) for x in rows] for tf, rows in higher.items()}
    trades: list[dict[str, Any]] = []
    decisions = {"CALL": 0, "PUT": 0, "NO_TRADE": 0}
    blocker_counts: dict[str, int] = {}
    i = 119
    while i + expiry_bars < len(base):
        decision_at = stamps[i] + timedelta(seconds=INTERVAL_SECONDS[interval])
        visible_higher: dict[str, list[dict[str, Any]]] = {}
        for tf, rows in higher.items():
            seconds = INTERVAL_SECONDS.get(tf)
            if not seconds:
                continue
            visible_higher[tf] = [
                row for row, stamp in zip(rows, higher_stamps[tf])
                if stamp is not None and stamp + timedelta(seconds=seconds) <= decision_at
            ]
        result = analyze_binary_options(
            base[: i + 1], symbol, interval, visible_higher, as_of=decision_at
        )
        decision = result["decision"]
        decisions[decision] = decisions.get(decision, 0) + 1
        for blocker in result.get("blockers", []):
            blocker_counts[blocker] = blocker_counts.get(blocker, 0) + 1
        if decision in {"CALL", "PUT"}:
            entry_index = i + 1
            trades.append({
                "direction": decision,
                "entry_index": entry_index,
                "expiry_bars": expiry_bars,
                "trade_id": f"{symbol}-{interval}-{entry_index}",
            })
            i = entry_index + expiry_bars - 1
        else:
            i += 1

    evaluation = evaluate_binary_trades(
        base, trades, payout=payout, stake=stake, initial_equity=initial_equity,
        tie_rule="refund",
    )
    test = evaluation["chronological_splits"]["test"]
    validation = evaluation["chronological_splits"]["validation"]
    sample_warnings = []
    if len(trades) < 30:
        sample_warnings.append("FEWER_THAN_30_TRADES")
    if test["trades"] < 10:
        sample_warnings.append("TEST_SPLIT_HAS_FEWER_THAN_10_TRADES")
    if test["win_rate_excluding_ties"] is None:
        sample_warnings.append("NO_DECISIVE_TEST_TRADES")
    break_even = 1.0 / (1.0 + payout)
    return {
        "symbol": symbol, "provider": "deriv", "interval": interval,
        "method": "strict_walk_forward_close_decision_next_open_entry",
        "lookahead_bias": False,
        "execution_enabled": False,
        "parameters": {"payout": payout, "stake": stake, "expiry_bars": expiry_bars,
                       "minimum_confluence": 72, "initial_equity": initial_equity},
        "candles_used": len(base), "decisions": decisions,
        "generated_trades": len(trades),
        "break_even_win_rate": round(break_even, 5),
        "overall": evaluation["overall"],
        "chronological_splits": evaluation["chronological_splits"],
        "validation_vs_test": {
            "validation_win_rate": validation["win_rate_excluding_ties"],
            "test_win_rate": test["win_rate_excluding_ties"],
            "validation_net_pnl": validation["net_pnl"],
            "test_net_pnl": test["net_pnl"],
            "test_expectancy": test["expectancy_per_trade"],
        },
        "blocker_frequency": dict(sorted(blocker_counts.items(), key=lambda x: x[1], reverse=True)),
        "warnings": sample_warnings,
        "interpretation": "Research simulation only. A positive historical result is not proof of future profitability; require a sufficiently large untouched test set and live forward observation.",
        "trades": evaluation["trades"],
    }
