# debug binance_client.py
import asyncio
import json
import websockets
from datetime import datetime, timezone

BINANCE_WS_URL = "wss://stream.binance.com:9443/ws/btcusdt@depth5@100ms"

async def run_binance(queue):
    reconnect_delay = 1
    while True:
        try:
            print("[binance] Connecting to depth5 stream...")
            async with websockets.connect(BINANCE_WS_URL, ping_interval=20, ping_timeout=20) as ws:
                print("[binance] Connected to depth5 stream.")
                count = 0
                async for raw in ws:
                    count += 1
                    try:
                        data = json.loads(raw)
                    except Exception:
                        print("[binance] Received non-json raw")
                        continue

                    # print first few raw messages
                    if count <= 8:
                        print(f"[binance] RAW #{count}: {json.dumps(data)[:400]}")
                    elif count == 9:
                        print("[binance] ...more messages (suppressing further raw prints)")

                    # Normalize: Binance sometimes wraps stream messages under 'e' / 'E' or 'data'
                    d = data.get("data") if "data" in data else data
                    if not d:
                        continue

                    bids = []
                    asks = []
                    if "bids" in d and "asks" in d:
                        bids = [[float(p), float(q)] for p, q in d.get("bids", [])][:5]
                        asks = [[float(p), float(q)] for p, q in d.get("asks", [])][:5]
                        ts = (datetime.fromtimestamp(d.get("E") / 1000, tz=timezone.utc).isoformat()
                              if d.get("E") else datetime.now(timezone.utc).isoformat())
                        await queue.put({
                            "exchange": "binance",
                            "type": "orderbook",
                            "bids": bids,
                            "asks": asks,
                            "timestamp": ts
                        })
        except Exception as e:
            print(f"[binance] Error: {e}, reconnecting in 2s...")
            await asyncio.sleep(reconnect_delay)
            reconnect_delay = min(reconnect_delay * 2, 30)
