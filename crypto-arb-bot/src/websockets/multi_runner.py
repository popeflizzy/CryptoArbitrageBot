import asyncio
import signal
import sys
from src.websockets.binance_client import run_binance
from src.websockets.okx_client import run_okx
from src.websockets.orderbook_manager import OrderBookManager

async def _main():
    queue = asyncio.Queue()
    obm = OrderBookManager()

    print("Starting multi_runner (Binance + OKX + OrderBookManager)...")

    tasks = [
        asyncio.create_task(run_binance(queue), name="binance"),
        asyncio.create_task(run_okx(queue), name="okx"),
        asyncio.create_task(obm.consume_queue(queue), name="consume"),
        asyncio.create_task(obm.monitor_loop(interval=3.0), name="monitor"),
    ]

    stop_event = asyncio.Event()

    def _shutdown():
        print("\n[system] Shutdown requested — stopping...")
        stop_event.set()

    loop = asyncio.get_running_loop()
    # best-effort to register signal handlers; some platforms (Windows) may not support add_signal_handler
    try:
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, _shutdown)
    except NotImplementedError:
        # Windows: fallback - KeyboardInterrupt will be caught in run()
        pass

    # wait until signal or stop_event set
    await stop_event.wait()

    # cancel tasks and wait for them
    print("[system] Cancelling tasks...")
    for t in tasks:
        t.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    print("[system] Shutdown complete. Bye 👋")

def run():
    try:
        asyncio.run(_main())
    except KeyboardInterrupt:
        # final fallback for windows Ctrl+C
        print("\n[system] Forced stop detected. Exiting...")

if __name__ == "__main__":
    run()
