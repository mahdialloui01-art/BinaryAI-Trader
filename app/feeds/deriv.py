import asyncio
import json
from datetime import datetime, timezone
from typing import AsyncIterator

import websockets

PUBLIC_WS = "wss://api.derivws.com/trading/v1/options/ws/public"
GRANULARITY = {"1m":60,"5m":300,"15m":900,"30m":1800,"1h":3600,"4h":14400,"1d":86400}

class DerivFeed:
    """Public, read-only Deriv market-data adapter. No account token is used."""
    name = "deriv"

    def __init__(self, url: str = PUBLIC_WS, timeout: float = 15.0):
        self.url = url
        self.timeout = timeout

    async def _request(self, payload: dict, expected: str):
        async with websockets.connect(self.url, open_timeout=self.timeout, ping_interval=20, ping_timeout=20) as ws:
            await ws.send(json.dumps(payload))
            while True:
                raw = await asyncio.wait_for(ws.recv(), timeout=self.timeout)
                msg = json.loads(raw)
                if msg.get("error"):
                    raise RuntimeError(msg["error"].get("message", "Deriv API error"))
                if msg.get("msg_type") == expected:
                    return msg

    async def symbols(self):
        msg = await self._request({"active_symbols":"brief"}, "active_symbols")
        return [
            {"symbol": item.get("symbol"), "name": item.get("display_name"),
             "display_name": item.get("display_name"), "market": item.get("market"),
             "market_display_name": item.get("market_display_name"),
             "submarket": item.get("submarket"), "exchange_is_open": item.get("exchange_is_open"),
             "provider": self.name}
            for item in msg.get("active_symbols", [])
            if item.get("symbol")
        ]

    async def contracts_for(self, symbol: str):
        msg = await self._request({"contracts_for": symbol}, "contracts_for")
        payload = msg.get("contracts_for", {})
        return {
            "provider": self.name,
            "symbol": symbol,
            "available": payload.get("available", []),
            "trading_period": payload.get("trading_period", []),
            "underlying": payload.get("underlying"),
        }

    async def candles(self, symbol: str, interval: str = "1m", limit: int = 300):
        granularity = GRANULARITY.get(interval)
        if not granularity:
            raise ValueError(f"Unsupported interval: {interval}")
        msg = await self._request({
            "ticks_history": symbol, "end": "latest", "style": "candles",
            "granularity": granularity, "count": min(max(int(limit), 1), 5000)
        }, "candles")
        result = []
        for bar in msg.get("candles", []):
            epoch = int(bar.get("epoch", 0))
            result.append({
                "provider": self.name, "symbol": symbol, "interval": interval,
                "timestamp": datetime.fromtimestamp(epoch, timezone.utc).isoformat().replace("+00:00","Z"),
                "openTime": datetime.fromtimestamp(epoch, timezone.utc).isoformat().replace("+00:00","Z"),
                "open": float(bar["open"]), "high": float(bar["high"]),
                "low": float(bar["low"]), "close": float(bar["close"]),
                "epoch": epoch
            })
        return result

    async def tick(self, symbol: str):
        msg = await self._request({"ticks": symbol, "subscribe": 1}, "tick")
        tick = msg.get("tick", {})
        quote = tick.get("quote")
        return {
            "provider": self.name, "symbol": tick.get("symbol", symbol),
            "price": quote, "mid": quote, "timestamp": datetime.fromtimestamp(
                int(tick.get("epoch", 0)), timezone.utc).isoformat().replace("+00:00","Z"),
            "stale": False, "source": "Deriv public WebSocket"
        }

    async def stream_ticks(self, symbol: str) -> AsyncIterator[dict]:
        async with websockets.connect(self.url, open_timeout=self.timeout, ping_interval=20, ping_timeout=20) as ws:
            await ws.send(json.dumps({"ticks": symbol, "subscribe": 1}))
            async for raw in ws:
                msg = json.loads(raw)
                if msg.get("error"):
                    raise RuntimeError(msg["error"].get("message", "Deriv stream error"))
                if msg.get("msg_type") != "tick":
                    continue
                tick = msg.get("tick", {})
                yield {
                    "provider": self.name, "symbol": tick.get("symbol", symbol),
                    "price": tick.get("quote"), "time": tick.get("epoch"),
                    "timestamp": datetime.fromtimestamp(int(tick.get("epoch",0)), timezone.utc).isoformat().replace("+00:00","Z")
                }
