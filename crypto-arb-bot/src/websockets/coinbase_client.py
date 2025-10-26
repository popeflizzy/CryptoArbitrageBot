# debug coinbase_client.py
import asyncio
import json
import websockets
from datetime import datetime, timezone

COINBASE_WS_URL = "wss://ws-feed.exchange.coinbase.com"
TRY_PRODUCTS = ["BTC-USD", "BTC-USDT", "BTC-USD-PERP"]  # try common variants

async def run_coinbase(queue):
    subscribe_template = {
        "type": "subscribe",
        "channels": [{"name": "level2", "product_ids": []}]
    }

    reconnect_delay = 1
    while True:
        for product in TRY_PRODUCTS:
            try:
                print(f"[coinbase] Attempt subscribe to {product}")
                async with websockets.connect(COINBASE_WS_URL, ping_interval=20, ping_timeout=20) as ws:
                    sub = subscribe_template.copy()
                    sub["channels"] = [{"name": "level2", "product_ids": [product]}]
                    await ws.send(json.dumps(sub))
                    print(f"[coinbase] Sent subscribe for {product}")

                    # wait for subscription ack or messages for 8s
                    seen_ack = False
                    msg_count = 0
                    async for raw in ws:
                        msg_count += 1
                        try:
                            data = json.loads(raw)
                        except Exception:
                            print("[coinbase] Received non-json message")
                            continue

                        # print subscription ack once
                        if not seen_ack and data.get("type") in ("subscriptions", "snapshot"):
                            print(f"[coinbase] Subscribe ack/snapshot for {product}: {data.get('type')}")
                            seen_ack = True

                        # print sample messages (first 6)
                        if msg_count <= 6:
                            print(f"[coinbase] RAW #{msg_count}: {json.dumps(data)[:400]}")
                        elif msg_count == 7:
                            print(f"[coinbase] ...more messages received (counting)")

                        # when l2update occurs, normalize and push
                        if data.get("type") == "l2update":
                            changes = data.get("changes", [])
                            bids, asks = [], []
                            for side, price, size in changes:
                                if side == "buy":
                                    bids.append([float(price), float(size)])
                                else:
                                    asks.append([float(price), float(size)])
                            ts = data.get("time") or datetime.now(timezone.utc).isoformat()
                            await queue.put({
                                "exchange": "coinbase",
                                "type": "orderbook",
                                "product": product,
                                "bids": bids,
                                "asks": asks,
                                "timestamp": ts
                            })

                        # break after some activity to allow checking next product if nothing useful
                        if msg_count > 50:
                            print(f"[coinbase] Received {msg_count} messages for {product}, staying connected.")
                            # keep connected indefinitely for this product
                            # but to avoid tight loops if product invalid, stay open
                            # continue reading
                    # end async for
            except Exception as e:
                print(f"[coinbase] Attempt {product} error: {e}")
                await asyncio.sleep(reconnect_delay)
                continue
        # if all products failed, wait then retry list
        print("[coinbase] All product attempts failed; sleeping before retrying products...")
        await asyncio.sleep(5)
