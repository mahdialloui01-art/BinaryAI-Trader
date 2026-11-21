from app.feeds.biquote import BiQuoteFeed
from app.feeds.otcharts import OTChartsFeed

class MarketDataService:
    def __init__(self, otcharts_api_key: str | None = None):
        self.reference = BiQuoteFeed()
        self.quotex = OTChartsFeed(otcharts_api_key) if otcharts_api_key else None

    async def health(self):
        return {
            "quotex_readonly": "configured" if self.quotex else "needs_otcharts_api_key",
            "real_market_reference": "configured",
            "execution": "disabled",
        }

    async def quotex_candles(self, symbol: str, timeframe_seconds: int = 60,
                             limit: int = 300):
        if not self.quotex:
            raise RuntimeError("Set OTCHARTS_API_KEY to enable the third-party read-only feed")
        return await self.quotex.candles(symbol, timeframe_seconds, limit, "quotex")

    async def reference_candles(self, symbol: str, interval: str = "1m",
                                limit: int = 300):
        return await self.reference.candles(symbol, interval, limit)

    async def reference_tick(self, symbol: str):
        return await self.reference.tick(symbol)
