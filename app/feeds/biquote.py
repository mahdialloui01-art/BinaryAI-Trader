from typing import Any
import httpx

BASE_URL = "https://biquote.io"

class BiQuoteFeed:
    """Read-only adapter for the documented BiQuote REST market-data API."""
    name = "biquote"

    def __init__(self, base_url: str = BASE_URL, timeout: float = 12.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    async def symbols(self) -> list[dict[str, Any]]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(f"{self.base_url}/api/symbols")
            response.raise_for_status()
            payload = response.json()
        return payload if isinstance(payload, list) else payload.get("symbols", [])

    async def tick(self, symbol: str) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(
                f"{self.base_url}/api/{symbol}",
                params={"allowStale": "false"},
            )
            response.raise_for_status()
            data = response.json()
        return {
            "provider": self.name, "symbol": data.get("symbol", symbol),
            "bid": data.get("bid"), "ask": data.get("ask"),
            "mid": data.get("mid"), "timestamp": data.get("timestamp"),
            "market_state": data.get("marketState"), "stale": data.get("stale"),
            "source": data.get("source"), "raw": data,
        }

    async def candles(self, symbol: str, interval: str = "1m",
                      limit: int = 300) -> list[dict[str, Any]]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(
                f"{self.base_url}/api/{symbol}/ohlc",
                params={"interval": interval, "limit": min(max(limit, 1), 1000)},
            )
            response.raise_for_status()
            payload = response.json()
        return [
            {"provider": self.name, "symbol": payload.get("symbol", symbol),
             "interval": payload.get("interval", interval), **bar}
            for bar in payload.get("bars", [])
        ]
