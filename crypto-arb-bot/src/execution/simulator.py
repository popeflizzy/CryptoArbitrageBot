import asyncio
import time
import csv
import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

SPREAD_THRESHOLD = float(os.getenv("SPREAD_THRESHOLD", 0.05))
TRADE_SIZE_USD = float(os.getenv("TRADE_SIZE_USD", 100.0))
SLIPPAGE_BPS = float(os.getenv("SLIPPAGE_BPS", 2))
COOLDOWN_SECONDS = float(os.getenv("COOLDOWN_SECONDS", 5))

class TradeSimulator:
    def __init__(self):
        self.last_trade_time = 0
        self.trade_id = 0
        self.cumulative_pnl = 0.0

        # Prepare output directory
        os.makedirs("data/sim_trades", exist_ok=True)
        self.filename = f"data/sim_trades/sim_trades_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

        with open(self.filename, mode="w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["id", "timestamp", "buy_ex", "sell_ex", "buy_price", "sell_price", "spread_pct", "pnl", "cum_pnl"])

    async def handle_signal(self, sim_queue: asyncio.Queue):
        print("[sim] Simulation engine running...")

        while True:
            trade = await sim_queue.get()
            current_time = time.time()

            if current_time - self.last_trade_time < COOLDOWN_SECONDS:
                continue

            self.last_trade_time = current_time
            self.trade_id += 1

            buy_ex = trade["buy_exchange"]
            sell_ex = trade["sell_exchange"]
            buy_price = trade["buy_price"]
            sell_price = trade["sell_price"]

            spread_pct = ((sell_price - buy_price) / buy_price) * 100

            if spread_pct < SPREAD_THRESHOLD:
                continue

            # Apply slippage (reduce profitability slightly)
            effective_buy = buy_price * (1 + SLIPPAGE_BPS / 10000)
            effective_sell = sell_price * (1 - SLIPPAGE_BPS / 10000)

            pnl = (effective_sell - effective_buy) * (TRADE_SIZE_USD / effective_buy)
            self.cumulative_pnl += pnl

            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            print(
                f"[sim] #{self.trade_id} {timestamp} BUY {buy_ex} @ {effective_buy:.2f} | "
                f"SELL {sell_ex} @ {effective_sell:.2f} | Spread={spread_pct:.4f}% | "
                f"PnL=${pnl:.2f} | Cum=${self.cumulative_pnl:.2f}"
            )

            with open(self.filename, mode="a", newline="") as f:
                writer = csv.writer(f)
                writer.writerow([
                    self.trade_id, timestamp, buy_ex, sell_ex,
                    effective_buy, effective_sell, spread_pct,
                    pnl, self.cumulative_pnl
                ])

async def run_simulation(sim_queue: asyncio.Queue):
    sim = TradeSimulator()
    await sim.handle_signal(sim_queue)
