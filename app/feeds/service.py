from app.feeds.deriv import DerivFeed
from app.feeds.otcharts import OTChartsFeed

class MarketDataService:
    def __init__(self, otcharts_api_key: str | None = None):
        self.reference = DerivFeed()
        self.quotex = OTChartsFeed(otcharts_api_key) if otcharts_api_key else None

    async def health(self):
        return {
            "primary": {
                "provider": "deriv",
                "configuration": "public_websocket_no_auth",
                "requires_api_key": False,
                "live_status": "not_probed",
                "market_data": "Deriv real and synthetic indices as listed by Deriv"
            },
            "legacy_quotex_readonly": {
                "provider": "otcharts",
                "configuration": "configured" if self.quotex else "disabled_optional",
                "note": "Not used by the primary app feed; not an official Quotex API."
            },
            "execution": "disabled",
            "policy": "Deriv public market data only; no trading or account authentication."
        }

    async def reference_symbols(self):
        return await self.reference.symbols()

    async def reference_candles(self, symbol: str, interval: str = "1m", limit: int = 300):
        return await self.reference.candles(symbol, interval, limit)

    async def reference_tick(self, symbol: str):
        return await self.reference.tick(symbol)

    async def stream_reference_ticks(self, symbol: str):
        async for tick in self.reference.stream_ticks(symbol):
            yield tick

    async def quotex_symbols(self):
        if not self.quotex:
            raise RuntimeError("Legacy optional OTCharts feed is disabled")
        return await self.quotex.symbols("quotex")

    async def open_quotex_stream(self, symbols: list[str]):
        if not self.quotex:
            raise RuntimeError("Legacy optional OTCharts feed is disabled")
        return await self.quotex.open_stream(symbols, "quotex")

    async def quotex_candles(self, symbol: str, timeframe_seconds: int = 60, limit: int = 300):
        if not self.quotex:
            raise RuntimeError("Legacy optional OTCharts feed is disabled")
        return await self.quotex.candles(symbol, timeframe_seconds, limit, "quotex")
