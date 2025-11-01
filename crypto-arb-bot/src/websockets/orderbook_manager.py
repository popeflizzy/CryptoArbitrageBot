import asyncio
from datetime import datetime, timezone

class OrderBookManager:
    """
    Consume normalized orderbook updates from multiple exchanges and compute best bid/ask.
    """

    def __init__(self):
        self.books = {}  # exchange -> data dict
        self._lock = asyncio.Lock()

    async def consume_queue(self, queue: asyncio.Queue):
        print("[orderbook] Manager consuming queue...")
        while True:
            try:
                msg = await queue.get()
            except asyncio.CancelledError:
                break

            if not isinstance(msg, dict):
                queue.task_done()
                continue

            exchange = msg.get("exchange")
            if not exchange:
                queue.task_done()
                continue

            async with self._lock:
                self.books[exchange] = {
                    "bids": msg.get("bids", []),
                    "asks": msg.get("asks", []),
                    "best_bid": msg.get("best_bid"),
                    "best_ask": msg.get("best_ask"),
                    "timestamp": msg.get("timestamp") or datetime.now(timezone.utc).isoformat()
                }

            bid = self.books[exchange]["best_bid"]
            ask = self.books[exchange]["best_ask"]
            print(f"[orderbook] Received update from {exchange}: bid={bid if bid is not None else 'N/A'} ask={ask if ask is not None else 'N/A'}")
            queue.task_done()

    async def monitor_loop(self, interval: float = 3.0):
        """
        Periodically prints a summary and looks for cross-exchange spreads.
        """
        while True:
            try:
                await asyncio.sleep(interval)
                async with self._lock:
                    if not self.books:
                        continue

                    print("\n[orderbook] === Summary ===")
                    for ex, data in self.books.items():
                        bid = data.get("best_bid")
                        ask = data.get("best_ask")
                        ts = data.get("timestamp")
                        bid_s = f"{bid:.2f}" if isinstance(bid, (int, float)) else "N/A"
                        ask_s = f"{ask:.2f}" if isinstance(ask, (int, float)) else "N/A"
                        print(f"{ex.upper():8} | bid={bid_s:<12} ask={ask_s:<12} ts={ts}")

                    # compute best bid (highest) and best ask (lowest)
                    valid_bids = [(ex, d["best_bid"]) for ex, d in self.books.items() if isinstance(d.get("best_bid"), (int, float))]
                    valid_asks = [(ex, d["best_ask"]) for ex, d in self.books.items() if isinstance(d.get("best_ask"), (int, float))]

                    if valid_bids and valid_asks:
                        best_bid_ex, best_bid = max(valid_bids, key=lambda t: t[1])
                        best_ask_ex, best_ask = min(valid_asks, key=lambda t: t[1])
                        spread = best_bid - best_ask
                        print(f"[orderbook] Best bid: {best_bid:.2f} ({best_bid_ex}) | Best ask: {best_ask:.2f} ({best_ask_ex}) | Spread: {spread:.2f}")
                        if spread > 0:
                            print(f"[orderbook] Potential arbitrage: SELL on {best_bid_ex} BUY on {best_ask_ex} | Spread = {spread:.2f}")
                    print("[orderbook] ==================\n")
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"[orderbook] monitor error: {e}")
                # continue looping
