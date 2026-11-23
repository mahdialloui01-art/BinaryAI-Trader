import asyncio
import json
import time
from datetime import datetime, timezone
from typing import AsyncIterator

import websockets

PUBLIC_WS = "wss://api.derivws.com/trading/v1/options/ws/public"
GRANULARITY = {"1m":60,"5m":300,"15m":900,"30m":1800,"1h":3600,"4h":14400,"1d":86400}

# Deriv can temporarily reject new public WebSocket handshakes with HTTP 429.
# Share a cooldown across Gold analysis requests in this Render worker so repeated
# button taps do not hammer the provider during its rate-limit window.
_GOLD_WS_COOLDOWN_UNTIL = 0.0
_GOLD_WS_COOLDOWN_SECONDS = 60.0

class DerivFeed:
    """Public, read-only Deriv market-data adapter. No account token is used."""
    name = "deriv"

    def __init__(self, url: str = PUBLIC_WS, timeout: float = 15.0):
        self.url = url
        self.timeout = timeout
        # Analysis fans out to several Deriv requests. Keep the connection count
        # bounded so a burst does not trigger provider-side WebSocket rejections.
        self._request_semaphore = asyncio.Semaphore(2)

    async def _request(self, payload: dict, expected: str):
        async with self._request_semaphore:
            last_error = None
            for attempt in range(3):
                try:
                    async with websockets.connect(
                        self.url, open_timeout=self.timeout,
                        ping_interval=20, ping_timeout=20,
                    ) as ws:
                        await ws.send(json.dumps(payload))
                        while True:
                            raw = await asyncio.wait_for(ws.recv(), timeout=self.timeout)
                            msg = json.loads(raw)
                            if msg.get("error"):
                                raise RuntimeError(msg["error"].get("message", "Deriv API error"))
                            if msg.get("msg_type") == expected:
                                return msg
                except RuntimeError:
                    # Provider-declared errors are not transient connection failures.
                    raise
                except (asyncio.TimeoutError, OSError, websockets.exceptions.WebSocketException) as exc:
                    last_error = exc
                    if attempt < 2:
                        # Back off more aggressively on provider handshake/rate-limit failures.
                        await asyncio.sleep(1.0 * (2 ** attempt))
            raise RuntimeError(f"Deriv WebSocket request failed after retry: {last_error}") from last_error

    async def symbols(self):
        msg = await self._request({"active_symbols":"brief"}, "active_symbols")
        # The current Deriv API renamed legacy symbol/display fields:
        # symbol -> underlying_symbol, display_name -> underlying_symbol_name.
        # Normalize both current and legacy responses for the Android client.
        result = []
        for item in msg.get("active_symbols", []):
            symbol = item.get("underlying_symbol") or item.get("symbol")
            if not symbol:
                continue
            display_name = item.get("underlying_symbol_name") or item.get("display_name") or symbol
            market = item.get("market") or ""
            result.append({
                "symbol": symbol,
                "name": display_name,
                "display_name": display_name,
                "market": market,
                "market_display_name": market.replace("_", " ").title(),
                "submarket": item.get("submarket"),
                "subgroup": item.get("subgroup"),
                "underlying_symbol_type": item.get("underlying_symbol_type") or item.get("symbol_type"),
                "exchange_is_open": bool(item.get("exchange_is_open")),
                "is_trading_suspended": bool(item.get("is_trading_suspended")),
                "pip_size": item.get("pip_size") or item.get("pip"),
                "provider": self.name
            })
        return result

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

    async def binary_contracts_for(self, symbol: str):
        """Return only fixed-payout/binary-style contracts advertised for an underlying."""
        response = await self.contracts_for(symbol)
        allowed_categories = {
            "callput", "highlow", "touchnotouch", "digits", "endsinout",
            "staysinout", "asian", "lookback", "resetcallput", "runhighlow",
        }
        contracts = []
        for item in response.get("available", []):
            category = str(item.get("contract_category") or "").lower()
            contract_type = str(item.get("contract_type") or "").upper()
            if category in allowed_categories and contract_type:
                contracts.append(item)
        return {
            "provider": self.name,
            "product": "binary_options",
            "symbol": symbol,
            "available": contracts,
            "binary_options_available": bool(contracts),
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }

    async def gold_analysis_snapshot(self, symbol: str):
        """Fetch the Gold quote and all analysis timeframes over ONE WebSocket handshake.

        Opening six independent sockets for a single analysis can trigger Deriv's
        HTTP 429 handshake limit, especially while the live tick stream is open.
        Requests are sent sequentially on one read-only public connection.
        """
        global _GOLD_WS_COOLDOWN_UNTIL
        remaining = _GOLD_WS_COOLDOWN_UNTIL - time.monotonic()
        if remaining > 0:
            raise RuntimeError(f"Deriv rate-limit cooldown active; retry in {int(remaining) + 1} seconds")

        requests = [
            ("quote", {"ticks": symbol}, "tick"),
            ("1m", {"ticks_history": symbol, "end": "latest", "style": "candles", "granularity": 60, "count": 120}, "candles"),
            ("5m", {"ticks_history": symbol, "end": "latest", "style": "candles", "granularity": 300, "count": 120}, "candles"),
            ("15m", {"ticks_history": symbol, "end": "latest", "style": "candles", "granularity": 900, "count": 120}, "candles"),
            ("1h", {"ticks_history": symbol, "end": "latest", "style": "candles", "granularity": 3600, "count": 100}, "candles"),
            ("4h", {"ticks_history": symbol, "end": "latest", "style": "candles", "granularity": 14400, "count": 100}, "candles"),
        ]
        responses = {}
        try:
            async with websockets.connect(
                self.url, open_timeout=self.timeout, ping_interval=20, ping_timeout=20,
            ) as ws:
                for req_id, (key, payload, expected) in enumerate(requests, start=1):
                    payload = {**payload, "req_id": req_id}
                    await ws.send(json.dumps(payload))
                    while True:
                        raw = await asyncio.wait_for(ws.recv(), timeout=self.timeout)
                        msg = json.loads(raw)
                        if msg.get("error"):
                            detail = msg["error"].get("message", "Deriv API error")
                            raise RuntimeError(detail)
                        if msg.get("req_id") == req_id and msg.get("msg_type") == expected:
                            responses[key] = msg
                            break
        except Exception as exc:
            message = str(exc)
            if "429" in message or "rate limit" in message.lower():
                _GOLD_WS_COOLDOWN_UNTIL = time.monotonic() + _GOLD_WS_COOLDOWN_SECONDS
                raise RuntimeError(
                    "Deriv rejected the WebSocket handshake with HTTP 429; "
                    "Gold analysis is paused for 60 seconds to respect the provider limit."
                ) from exc
            raise

        tick = responses["quote"].get("tick", {})
        epoch = int(tick.get("epoch", 0))
        quote = {
            "provider": self.name, "symbol": tick.get("symbol", symbol),
            "price": tick.get("quote"), "mid": tick.get("quote"),
            "timestamp": datetime.fromtimestamp(epoch, timezone.utc).isoformat().replace("+00:00", "Z"),
            "stale": False, "source": "Deriv public WebSocket"
        }
        candles = {}
        for interval in ("1m", "5m", "15m", "1h", "4h"):
            candles[interval] = []
            for bar in responses[interval].get("candles", []):
                stamp = int(bar.get("epoch", 0))
                iso = datetime.fromtimestamp(stamp, timezone.utc).isoformat().replace("+00:00", "Z")
                candles[interval].append({
                    "provider": self.name, "symbol": symbol, "interval": interval,
                    "timestamp": iso, "openTime": iso,
                    "open": float(bar["open"]), "high": float(bar["high"]),
                    "low": float(bar["low"]), "close": float(bar["close"]),
                    "epoch": stamp
                })
        return quote, candles

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
