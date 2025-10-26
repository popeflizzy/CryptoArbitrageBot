# debug multi_runner.py
import asyncio
from src.websockets.binance_client import run_binance
from src.websockets.coinbase_client import run_coinbase
from src.websockets.orderbook_manager import OrderBookManager

async def main():
    q = asyncio.Queue()
    obm = OrderBookManager()
    await asyncio.gather(
        run_binance(q),
        run_coinbase(q),
        obm.run(q)
    )

if __name__ == "__main__":
    asyncio.run(main())
