from app.feeds.biquote import BiQuoteFeed
from app.feeds.otcharts import OTChartsFeed


class MarketDataService:
    def __init__(self, otcharts_api_key: str | None = None):
        self.reference = BiQuoteFeed()
        self.quotex = OTChartsFeed(otcharts_api_key) if otcharts_api_key else None

    async def health(self):
        return {
            "real_market_reference": {
                "provider": "biquote",
                "configuration": "public_read_only_endpoint",
                "requires_api_key": False,
                "live_status": "not_probed",
            },
            "quotex_readonly": {
                "provider": "otcharts",
                "configuration": "configured" if self.quotex else "disabled_optional",
                "requires_paid_or_trial_plan": "unknown",
                "live_status": "not_probed",
            },
            "execution": "disabled",
            "policy": "Free-first core; optional provider never blocks reference-data endpoints.",
        }

    async def reference_symbols(self):
        return await self.reference.symbols()

    async def quotex_symbols(self):
        if not self.quotex:
            raise RuntimeError("Optional OTCharts feed is disabled; set OTCHARTS_API_KEY on the server")
        return await self.quotex.symbols("quotex")

    async def open_quotex_stream(self, symbols: list[str]):
        if not self.quotex:
            raise RuntimeError("Optional OTCharts feed is disabled; set OTCHARTS_API_KEY on the server")
        return await self.quotex.open_stream(symbols, "quotex")

    async def quotex_candles(self, symbol: str, timeframe_seconds: int = 60,
                             limit: int = 300):
        if not self.quotex:
            raise RuntimeError("Optional OTCharts feed is disabled; no paid dependency is required for the core")
        return await self.quotex.candles(symbol, timeframe_seconds, limit, "quotex")

    async def reference_candles(self, symbol: str, interval: str = "1m",
                                limit: int = 300):
        return await self.reference.candles(symbol, interval, limit)

    async def reference_tick(self, symbol: str):
        return await self.reference.tick(symbol)
