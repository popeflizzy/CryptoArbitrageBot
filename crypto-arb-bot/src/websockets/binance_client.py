import asyncio
import json
import aiohttp
from datetime import datetime, timezone

BINANCE_WS_URL = "wss://stream.binance.com:9443/ws/btcusdt@depth5"


async def run_binance(queue: asyncio.Queue):
    """
    Binance public depth5 stream -> normalized messages pushed to queue.
    Schema pushed:
    {
      "exchange": "binance",
      "bids": [[price, size], ...],
      "asks": [[price, size], ...],
      "best_bid": float or None,
      "best_ask": float or None,
      "timestamp": ISO str
    }
    """
    backoff = 1
    while True:
        try:
            print("[binance] Connecting to depth5 stream...")
            async with aiohttp.ClientSession() as session:
                async with session.ws_connect(BINANCE_WS_URL, heartbeat=20) as ws:
                    print("[binance] Connected to depth5 stream.")
                    backoff = 1
                    async for msg in ws:
                        if msg.type != aiohttp.WSMsgType.TEXT:
                            continue
                        try:
                            data = json.loads(msg.data)
                        except Exception:
                            continue

                        # Some endpoints wrap under "data" — handle both shapes
                        d = data.get("data", data)

                        # Binance depth5 typically has "bids" and "asks"
                        bids_raw = d.get("bids") or []
                        asks_raw = d.get("asks") or []

                        # ensure lists of [price, size]
                        bids = []
                        asks = []
                        try:
                            for p, q in bids_raw:
                                bids.append([float(p), float(q)])
                            for p, q in asks_raw:
                                asks.append([float(p), float(q)])
                        except Exception:
                            # ignore malformed message
                            continue

                        best_bid = bids[0][0] if bids else None
                        best_ask = asks[0][0] if asks else None
                        ts = datetime.now(timezone.utc).isoformat()

                        await queue.put({
                            "exchange": "binance",
                            "bids": bids,
                            "asks": asks,
                            "best_bid": best_bid,
                            "best_ask": best_ask,
                            "timestamp": ts,
                        })
        except Exception as e:
            print(f"[binance] Connection error: {e}, reconnecting in {backoff}s...")
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30)
