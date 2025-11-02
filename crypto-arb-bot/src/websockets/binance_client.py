import asyncio
import json
import time
import aiohttp

async def run_binance(queue):
    """
    Connects to Binance WebSocket (BTCUSDT depth5), streams best bid/ask data,
    and pushes updates into the shared asyncio queue for the orderbook manager.
    """
    url = "wss://stream.binance.com:9443/ws/btcusdt@depth5"
    print("[binance] Connecting to depth5 stream...")

    while True:  # auto-reconnect loop
        try:
            async with aiohttp.ClientSession() as session:
                async with session.ws_connect(url, heartbeat=30) as ws:
                    print("[binance] Connected to depth5 stream.")

                    async for msg in ws:
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            try:
                                data = json.loads(msg.data)
                                bids = data.get("bids", [])
                                asks = data.get("asks", [])
                                if not bids or not asks:
                                    continue

                                best_bid = float(bids[0][0])
                                best_ask = float(asks[0][0])

                                await queue.put({
                                    "exchange": "binance",
                                    "best_bid": best_bid,
                                    "best_ask": best_ask,
                                    "timestamp": time.time(),
                                })
                            except Exception as e:
                                print(f"[binance] JSON parse error: {e}")
                                continue

                        elif msg.type == aiohttp.WSMsgType.ERROR:
                            print("[binance] WebSocket error, reconnecting...")
                            break

        except aiohttp.ClientConnectionError as e:
            print(f"[binance] Connection error: {e}, retrying in 2s...")
            await asyncio.sleep(2)
        except Exception as e:
            print(f"[binance] Unexpected error: {e}, retrying in 2s...")
            await asyncio.sleep(2)
