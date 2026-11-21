import pytest

from app.research.backtest import evaluate_binary_trades


@pytest.fixture
def candles():
    closes = [101, 99, 100, 102, 98, 100, 103, 97, 101, 99]
    return [
        {"timestamp": f"2026-01-01T00:{i:02d}:00Z", "open": 100, "high": max(100, c) + 1,
         "low": min(100, c) - 1, "close": c}
        for i, c in enumerate(closes)
    ]


def test_call_put_and_payout_metrics(candles):
    result = evaluate_binary_trades(candles, [
        {"direction": "CALL", "entry_index": 0, "expiry_bars": 1},
        {"direction": "PUT", "entry_index": 1, "expiry_bars": 1},
    ], payout=0.8, stake=2)
    assert result["overall"]["wins"] == 2
    assert result["overall"]["net_pnl"] == 3.2


def test_tie_refund_and_tie_as_loss(candles):
    refund = evaluate_binary_trades(candles, [{"direction": "CALL", "entry_index": 2}], tie_rule="refund")
    loss = evaluate_binary_trades(candles, [{"direction": "CALL", "entry_index": 2}], tie_rule="loss")
    assert refund["overall"]["ties"] == 1
    assert refund["overall"]["net_pnl"] == 0
    assert loss["overall"]["net_pnl"] == -1


def test_expiry_outside_data_rejected(candles):
    with pytest.raises(ValueError, match="outside"):
        evaluate_binary_trades(candles, [{"direction": "CALL", "entry_index": 9, "expiry_bars": 2}])


def test_bad_ohlc_rejected(candles):
    candles[0]["high"] = 50
    with pytest.raises(ValueError, match="Invalid OHLC"):
        evaluate_binary_trades(candles, [])


def test_chronological_splits_and_loss_streak(candles):
    result = evaluate_binary_trades(candles, [
        {"direction": "PUT", "entry_index": 0},
        {"direction": "PUT", "entry_index": 1},
        {"direction": "CALL", "entry_index": 2},
    ])
    assert result["overall"]["max_consecutive_losses"] == 2
    assert set(result["chronological_splits"]) == {"train", "validation", "test"}


def test_duplicate_trade_index_rejected(candles):
    with pytest.raises(ValueError, match="Duplicate"):
        evaluate_binary_trades(candles, [
            {"direction": "CALL", "entry_index": 0},
            {"direction": "PUT", "entry_index": 0},
        ])
