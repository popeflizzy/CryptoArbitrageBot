import logging

class OrderBookManager:
    def __init__(self):
        self.books = {}
        logging.info("[orderbook] Manager consuming queue...")

    async def consume_queue(self, queue):
        """Continuously read updates from WebSocket queue."""
        while True:
            try:
                data = await queue.get()  # only ONE value (a dict)
                exchange = data["exchange"]
                self.books[exchange] = data
                self.detect_arbitrage()  # call arbitrage check
            except Exception as e:
                logging.error(f"[orderbook] Error processing message: {e}")

    def detect_arbitrage(self):
        """Detect arbitrage opportunities and simulate execution."""
        if "binance" not in self.books or "okx" not in self.books:
            return

        bnb = self.books["binance"]
        okx = self.books["okx"]

        # Parameters
        threshold_pct = 0.05     # Minimum profit % to consider
        trade_size_usdt = 1000   # Simulated trade notional size
        fee_pct = 0.04 / 100     # 0.04% per trade

        # Buy on OKX, sell on Binance
        if okx["best_ask"] < bnb["best_bid"]:
            spread = bnb["best_bid"] - okx["best_ask"]
            pct = (spread / okx["best_ask"]) * 100
            if pct > threshold_pct:
                est_profit = trade_size_usdt * (pct / 100)
                est_fee = trade_size_usdt * 2 * fee_pct
                net = est_profit - est_fee
                print(
                    f"🚀 BUY OKX {okx['best_ask']} / SELL BINANCE {bnb['best_bid']} "
                    f"(+{pct:.3f}%) | Profit≈${net:.2f} after fees"
                )

        # Buy on Binance, sell on OKX
        if bnb["best_ask"] < okx["best_bid"]:
            spread = okx["best_bid"] - bnb["best_ask"]
            pct = (spread / bnb["best_ask"]) * 100
            if pct > threshold_pct:
                est_profit = trade_size_usdt * (pct / 100)
                est_fee = trade_size_usdt * 2 * fee_pct
                net = est_profit - est_fee
                print(
                    f"🚀 BUY BINANCE {bnb['best_ask']} / SELL OKX {okx['best_bid']} "
                    f"(+{pct:.3f}%) | Profit≈${net:.2f} after fees"
                )
