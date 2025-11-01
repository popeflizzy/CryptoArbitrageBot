import asyncio
import json
import aiohttp
from datetime import datetime, timezone

OKX_WS_URL = "wss://ws.okx.com:8443/ws/v5/public"
PAIR = "BTC-USDT"


async def run_okx(queue: asyncio.Queue):
    """
    OKX books5 -> normalized messages pushed to queue.
    """
    backoff = 1
    while True:
        try:
            print("[okx] Connecting to books5 stream...")
            async with aiohttp.ClientSession() as session:
                async with session.ws_connect(OKX_WS_URL, heartbeat=20) as ws:
                    # subscribe
                    sub = {"op": "subscribe", "args": [{"channel": "books5", "instId": PAIR}]}
                    await ws.send_json(sub)
                    print(f"[okx] Subscribed to {PAIR}")
                    backoff = 1

                    async for msg in ws:
                        if msg.type != aiohttp.WSMsgType.TEXT:
                            continue
                        try:
                            data = json.loads(msg.data)
                        except Exception:
                            continue

                        # OKX sends {"action":..., "arg":..., "data":[{...}]}
                        data_chunk = None
                        if "data" in data and isinstance(data["data"], list) and data["data"]:
                            data_chunk = data["data"][0]
                        elif "arg" in data and "data" in data:
                            # unlikely but safe
                            data_chunk = data["data"][0] if data["data"] else None

                        if not data_chunk:
                            continue

                        bids_raw = data_chunk.get("bids", [])
                        asks_raw = data_chunk.get("asks", [])
                        # OKX bids/asks may be [["price","size",...], ...]
                        bids = []
                        asks = []
                        try:
                            for item in bids_raw:
                                price = float(item[0])
                                size = float(item[1])
                                bids.append([price, size])
                            for item in asks_raw:
                                price = float(item[0])
                                size = float(item[1])
                                asks.append([price, size])
                        except Exception:
                            continue

                        if not bids or not asks:
                            continue

                        best_bid = bids[0][0]
                        best_ask = asks[0][0]
                        ts = datetime.now(timezone.utc).isoformat()

                        await queue.put({
                            "exchange": "okx",
                            "bids": bids,
                            "asks": asks,
                            "best_bid": best_bid,
                            "best_ask": best_ask,
                            "timestamp": ts,
                        })
        except Exception as e:
            print(f"[okx] Error: {e}, reconnecting in {backoff}s...")
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30)
