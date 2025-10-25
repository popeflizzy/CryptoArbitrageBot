"""
coinbase_client.py
------------------
Async WebSocket client for Coinbase.
Streams trades, ticker, and level2 orderbook for BTC/USDT.
Yields (timestamp_received, latency_ms) for multi_runner.
"""

import asyncio
import json
import websockets
from datetime import datetime, timezone

COINBASE_URL = "wss://ws-feed.exchange.coinbase.com"
PRODUCT_ID = "BTC-USDT"
CHANNELS = ["ticker", "matches", "level2"]


async def subscribe(ws):
    sub_msg = {
        "type": "subscribe",
        "product_ids": [PRODUCT_ID],
        "channels": CHANNELS,
    }
    await ws.send(json.dumps(sub_msg))
    print("[coinbase] Connected & subscribed.")


async def handler(ws):
    async for msg in ws:
        now = datetime.now(timezone.utc)
        data = json.loads(msg)

        # Coinbase has "time" field in ISO format for most messages
        server_time = data.get("time")
        if server_time:
            try:
                event_dt = datetime.fromisoformat(server_time.replace("Z", "+00:00"))
                latency = (now - event_dt).total_seconds() * 1000  # ms
                yield now.isoformat(), latency
            except Exception:
                continue


async def run_coinbase():
    """Connects to Coinbase websocket, handles auto-reconnect & yields messages."""
    while True:
        try:
            async with websockets.connect(COINBASE_URL, ping_interval=20) as ws:
                await subscribe(ws)
                async for tick in handler(ws):
                    yield tick
        except Exception as e:
            print(f"[coinbase] Error: {e}, reconnecting in 3s...")
            await asyncio.sleep(3)
