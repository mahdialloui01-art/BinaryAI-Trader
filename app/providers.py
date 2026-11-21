from abc import ABC, abstractmethod

from app.models import Candle, Tick


class MarketDataProvider(ABC):
    """Implement only against a provider's documented, authorized data interface."""

    name: str

    @abstractmethod
    async def get_latest_tick(self, symbol: str) -> Tick:
        raise NotImplementedError

    @abstractmethod
    async def get_candles(self, symbol: str, timeframe_seconds: int,
                          limit: int = 100) -> list[Candle]:
        raise NotImplementedError


class DisabledProvider(MarketDataProvider):
    name = "disabled"

    async def get_latest_tick(self, symbol: str) -> Tick:
        raise RuntimeError("No authorized market-data provider is configured")

    async def get_candles(self, symbol: str, timeframe_seconds: int,
                          limit: int = 100) -> list[Candle]:
        raise RuntimeError("No authorized market-data provider is configured")


class QuotexProviderUnavailable:
    """Placeholder only.

    Do not implement with private endpoints, reverse engineering, browser/session
    scraping, or automated account interaction. Enable only if Quotex supplies a
    documented interface and explicitly authorizes this use.
    """
    enabled = False
    reason = "No verified public authorized API configured"
