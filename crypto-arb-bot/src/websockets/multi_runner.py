import asyncio
import logging

from src.websockets.binance_client import run_binance
from src.websockets.okx_client import run_okx
from src.websockets.orderbook_manager import OrderBookManager
from src.execution.simulated_executor import SimulatedExecutor

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
logger = logging.getLogger(__name__)


async def _main():
    queue = asyncio.Queue()

    obm = OrderBookManager()
    executor = SimulatedExecutor(obm)
    obm.executor = executor

    logger.info("Starting multi_runner (Binance + OKX + OrderBookManager)...")

    # run_binance and run_okx are async functions (not classes)
    tasks = [
        asyncio.create_task(run_binance(queue)),
        asyncio.create_task(run_okx(queue)),
        asyncio.create_task(obm.consume_queue(queue)),
    ]

    await asyncio.gather(*tasks)


def run():
    try:
        asyncio.run(_main())
    except KeyboardInterrupt:
        logger.info("Shutdown requested — closing gracefully.")


if __name__ == "__main__":
    run()
