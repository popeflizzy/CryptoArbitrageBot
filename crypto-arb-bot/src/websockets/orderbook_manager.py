# debug orderbook_manager.py
import asyncio
from collections import defaultdict
from datetime import datetime, timezone

class OrderBookManager:
    def __init__(self):
        # store latest per exchange
        self.latest = {}
        self.counts = defaultdict(int)

    async def run(self, queue):
        print("[orderbook] Manager started — waiting for normalized messages...")
        while True:
            msg = await queue.get()
            ex = msg.get("exchange")
            typ = msg.get("type")
            self.counts[ex] += 1
            self.latest[ex] = msg

            print(f"[orderbook] Received {typ} from {ex} (count={self.counts[ex]})")
            # print a short preview
            bids = msg.get("bids") or []
            asks = msg.get("asks") or []
            if bids and asks:
                b_bid = bids[0][0]
                b_ask = asks[0][0]
                print(f"[orderbook] {ex} best bid={b_bid} ask={b_ask} ts={msg.get('timestamp')}")
            else:
                print(f"[orderbook] {ex} had no bids/asks in this message.")

            # if both exchanges have recent data, print spread
            if "binance" in self.latest and "coinbase" in self.latest:
                bb = self.latest["binance"]["bids"][0][0] if self.latest["binance"]["bids"] else None
                ba = self.latest["binance"]["asks"][0][0] if self.latest["binance"]["asks"] else None
                cb = self.latest["coinbase"]["bids"][0][0] if self.latest["coinbase"]["bids"] else None
                ca = self.latest["coinbase"]["asks"][0][0] if self.latest["coinbase"]["asks"] else None
                if all(x is not None for x in (bb, ba, cb, ca)):
                    diff = round(cb - ba, 4)
                    print(f"[orderbook] SpreadDiff (coinbase_bid - binance_ask) = {diff}")
