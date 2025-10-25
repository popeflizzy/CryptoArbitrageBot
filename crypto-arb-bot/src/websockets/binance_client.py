"""
binance_client.py
-----------------
Async WebSocket client for Binance.
Streams trades, ticker, and orderbook for BTC/USDT.
Yields (timestamp_received, latency_ms) for multi_runner.
"""

import asyncio
import json
import websockets
from datetime import datetime, timezone

BINANCE_URL = "wss://stream.binance.com:9443/ws"
SYMBOL = "btcusdt"
CHANNELS = [
    f"{SYMBOL}@trade",
    f"{SYMBOL}@ticker",
    f"{SYMBOL}@depth5@100ms",  # top 5 orderbook updates
]


async def subscribe(ws):
    sub_msg = {
        "method": "SUBSCRIBE",
        "params": CHANNELS,
        "id": 1,
    }
    await ws.send(json.dumps(sub_msg))
    print("[binance] Subscribed to trade, ticker, and depth5 channels.")


async def handler(ws):
    async for msg in ws:
        now = datetime.now(timezone.utc)
        data = json.loads(msg)

        # Binance sends many types; handle trade, ticker, or depth
        event_type = data.get("e")

        # Each event contains a server timestamp "T" or "E"
        event_ts = data.get("T") or data.get("E")
        if event_ts:
            event_dt = datetime.fromtimestamp(event_ts / 1000, tz=timezone.utc)
            latency = (now - event_dt).total_seconds() * 1000  # ms
            yield now.isoformat(), latency


async def run_binance():
    """Connects to Binance websocket, handles auto-reconnect & yields messages."""
    while True:
        try:
            async with websockets.connect(BINANCE_URL, ping_interval=20) as ws:
                await subscribe(ws)
                print("[binance] Connected.")
                async for tick in handler(ws):
                    yield tick
        except Exception as e:
            print(f"[binance] Error: {e}, reconnecting in 3s...")
            await asyncio.sleep(3)
