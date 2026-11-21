from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from app.models import Candle, MarketKind, Tick
from app.quality import age_seconds, compare_prices, tick_is_fresh


def test_candle_rejects_invalid_ohlc():
    with pytest.raises(ValidationError):
        Candle(
            provider="test", symbol="EURUSD", market_kind=MarketKind.REAL,
            timeframe_seconds=60, timestamp=datetime.now(timezone.utc),
            open=1.1, high=1.0, low=0.9, close=1.05,
        )


def test_tick_freshness():
    now = datetime.now(timezone.utc)
    tick = Tick(provider="test", symbol="EURUSD", price=1.1,
                timestamp=now - timedelta(seconds=3))
    assert tick_is_fresh(tick, max_age_seconds=5, now=now)
    assert not tick_is_fresh(tick, max_age_seconds=2, now=now)


def test_price_comparison():
    result = compare_prices(100.0, 100.02, tolerance=0.03)
    assert result["within_tolerance"] is True
    assert result["absolute_difference"] == pytest.approx(0.02)


def test_age_never_negative():
    now = datetime.now(timezone.utc)
    assert age_seconds(now + timedelta(seconds=5), now) == 0
