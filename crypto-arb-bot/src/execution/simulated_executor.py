import logging
import asyncio
import time

logger = logging.getLogger(__name__)

class SimulatedExecutor:
    def __init__(self, orderbook_manager=None):
        """
        :param orderbook_manager: Optional link to OrderBookManager for feedback
        """
        self.orderbook_manager = orderbook_manager
        self.trades = []

    async def execute_trade(self, buy_exchange, sell_exchange, pct_spread):
        """Simulate an arbitrage trade."""
        trade = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "buy_exchange": buy_exchange,
            "sell_exchange": sell_exchange,
            "spread": round(pct_spread, 4),
        }

        # Log + print
        logger.info(f"[EXECUTOR] Simulated trade: {buy_exchange} → {sell_exchange} (+{pct_spread:.3f}%)")
        print(f"[EXECUTOR] ✅ Simulated trade executed: BUY {buy_exchange} → SELL {sell_exchange} (+{pct_spread:.3f}%)")

        self.trades.append(trade)

        # Optional feedback (e.g., notify manager)
        if self.orderbook_manager:
            await asyncio.sleep(0.1)
            logger.info("[EXECUTOR] Notified orderbook manager of simulated trade.")
