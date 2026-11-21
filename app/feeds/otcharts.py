import httpx
from typing import Sequence

class OTChartsFeed:
    """Read-only third-party OTCharts adapter. Never uses Quotex credentials."""
    name = "otcharts"

    def __init__(self, api_key: str, base_url: str = "https://otcharts.com",
                 timeout: float = 15.0):
        if not api_key:
            raise ValueError("OTCHARTS_API_KEY is required")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _headers(self):
        return {"Authorization": f"Bearer {self.api_key}"}

    async def symbols(self, venue: str = "quotex"):
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(
                f"{self.base_url}/v1/symbols",
                params={"venue": venue}, headers=self._headers(),
            )
            response.raise_for_status()
            return response.json()

    async def open_stream(self, symbols: Sequence[str], venue: str = "quotex"):
        """Open one upstream SSE connection; caller owns and must close both objects."""
        client = httpx.AsyncClient(timeout=None)
        request = client.build_request(
            "GET",
            f"{self.base_url}/v1/stream",
            params={"venue": venue, "symbol": ",".join(symbols)},
            headers={**self._headers(), "Accept": "text/event-stream"},
        )
        try:
            response = await client.send(request, stream=True)
            response.raise_for_status()
            return client, response
        except Exception:
            await client.aclose()
            raise

    async def candles(self, symbol: str, timeframe_seconds: int = 60,
                      limit: int = 300, venue: str = "quotex"):
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(
                f"{self.base_url}/v1/candles",
                params={"venue": venue, "symbol": symbol,
                        "tf": timeframe_seconds, "limit": min(max(limit, 1), 5000)},
                headers=self._headers(),
            )
            response.raise_for_status()
            payload = response.json()
        return [
            {"provider": self.name, "venue": venue, "symbol": symbol, **bar}
            for bar in payload.get("candles", [])
        ]
