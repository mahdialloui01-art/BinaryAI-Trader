from __future__ import annotations

from typing import Any


def _metrics(results: list[dict[str, Any]], initial_equity: float) -> dict[str, Any]:
    wins = sum(r["outcome"] == "WIN" for r in results)
    losses = sum(r["outcome"] == "LOSS" for r in results)
    ties = sum(r["outcome"] == "TIE" for r in results)
    decisive = wins + losses
    equity = initial_equity
    peak = equity
    max_drawdown = 0.0
    losing_streak = current_streak = 0
    pnl_values = []
    for result in results:
        pnl = result["pnl"]
        pnl_values.append(pnl)
        equity += pnl
        peak = max(peak, equity)
        if peak > 0:
            max_drawdown = max(max_drawdown, (peak - equity) / peak)
        if result["outcome"] == "LOSS":
            current_streak += 1
            losing_streak = max(losing_streak, current_streak)
        elif result["outcome"] == "WIN":
            current_streak = 0
    total_pnl = sum(pnl_values)
    return {
        "trades": len(results),
        "wins": wins,
        "losses": losses,
        "ties": ties,
        "win_rate_excluding_ties": wins / decisive if decisive else None,
        "win_rate_ties_as_losses": wins / (wins + losses + ties) if results else None,
        "net_pnl": round(total_pnl, 8),
        "expectancy_per_trade": round(total_pnl / len(results), 8) if results else None,
        "max_consecutive_losses": losing_streak,
        "max_drawdown_fraction": round(max_drawdown, 8),
        "ending_equity": round(equity, 8),
    }


def evaluate_binary_trades(
    candles: list[dict[str, Any]],
    trades: list[dict[str, Any]],
    payout: float = 0.80,
    stake: float = 1.0,
    initial_equity: float = 100.0,
    tie_rule: str = "refund",
    train_fraction: float = 0.60,
    validation_fraction: float = 0.20,
) -> dict[str, Any]:
    """Evaluate explicit historical CALL/PUT entries without generating signals.

    entry_index points to the candle whose OPEN is the contract entry.
    expiry_bars=1 settles at that candle's CLOSE. No future candle is used
    to determine the entry price.
    """
    if len(candles) < 2:
        raise ValueError("At least two chronological candles are required")
    if not 0 < payout <= 1:
        raise ValueError("payout must be greater than 0 and at most 1")
    if stake <= 0 or initial_equity <= 0:
        raise ValueError("stake and initial_equity must be positive")
    if tie_rule not in {"refund", "loss"}:
        raise ValueError("tie_rule must be 'refund' or 'loss'")
    if not 0 < train_fraction < 1 or not 0 < validation_fraction < 1 or train_fraction + validation_fraction >= 1:
        raise ValueError("train_fraction + validation_fraction must be below 1")

    previous_timestamp = None
    for i, candle in enumerate(candles):
        try:
            o, h, low, c = (float(candle[k]) for k in ("open", "high", "low", "close"))
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"Malformed OHLC candle at index {i}") from exc
        if min(o, h, low, c) <= 0 or h < max(o, c, low) or low > min(o, c, h):
            raise ValueError(f"Invalid OHLC values at index {i}")
        timestamp = candle.get("timestamp", candle.get("time"))
        if timestamp is not None:
            if previous_timestamp is not None and str(timestamp) <= str(previous_timestamp):
                raise ValueError("Candles must be strictly chronological")
            previous_timestamp = timestamp

    normalized = []
    seen = set()
    for number, trade in enumerate(trades):
        direction = str(trade.get("direction", "")).upper()
        if direction not in {"CALL", "PUT"}:
            raise ValueError(f"Trade {number}: direction must be CALL or PUT")
        try:
            entry_index = int(trade["entry_index"])
            expiry_bars = int(trade.get("expiry_bars", 1))
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"Trade {number}: invalid entry_index or expiry_bars") from exc
        settle_index = entry_index + expiry_bars - 1
        if entry_index < 0 or expiry_bars < 1 or settle_index >= len(candles):
            raise ValueError(f"Trade {number}: entry or expiry is outside available candles")
        if entry_index in seen:
            raise ValueError(f"Duplicate trade entry_index: {entry_index}")
        seen.add(entry_index)
        entry = float(candles[entry_index]["open"])
        exit_price = float(candles[settle_index]["close"])
        if direction == "CALL":
            outcome = "WIN" if exit_price > entry else "LOSS" if exit_price < entry else "TIE"
        else:
            outcome = "WIN" if exit_price < entry else "LOSS" if exit_price > entry else "TIE"
        pnl = stake * payout if outcome == "WIN" else -stake if outcome == "LOSS" or tie_rule == "loss" else 0.0
        normalized.append({
            "trade_id": trade.get("trade_id", str(number + 1)),
            "direction": direction,
            "entry_index": entry_index,
            "settle_index": settle_index,
            "entry_price": entry,
            "settlement_price": exit_price,
            "expiry_bars": expiry_bars,
            "outcome": outcome,
            "pnl": round(pnl, 8),
        })

    normalized.sort(key=lambda item: item["entry_index"])
    n = len(candles)
    train_end = int(n * train_fraction)
    validation_end = int(n * (train_fraction + validation_fraction))
    splits = {"train": [], "validation": [], "test": []}
    for result in normalized:
        index = result["entry_index"]
        key = "train" if index < train_end else "validation" if index < validation_end else "test"
        splits[key].append(result)

    return {
        "method": "fixed_entry_index_open_to_expiry_close",
        "payout": payout,
        "stake": stake,
        "tie_rule": tie_rule,
        "lookahead_note": "Entry uses the selected candle OPEN; settlement uses its close at the configured expiry. Signals themselves are supplied by the caller and are not generated or validated here.",
        "overall": _metrics(normalized, initial_equity),
        "chronological_splits": {
            name: {
                "entry_index_range": [0, train_end - 1] if name == "train" else
                    [train_end, validation_end - 1] if name == "validation" else
                    [validation_end, n - 1],
                **_metrics(items, initial_equity),
            }
            for name, items in splits.items()
        },
        "trades": normalized,
    }
