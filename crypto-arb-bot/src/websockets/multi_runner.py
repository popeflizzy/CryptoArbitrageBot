# src/websockets/multi_runner.py
"""
Multi-Exchange WebSocket Runner with Shared Latency Comparator.
Runs Binance and Coinbase concurrently and compares data latency in real time.
"""

import asyncio
import signal
import time
import json
from pathlib import Path
from collections import deque
from statistics import mean

# import clients
import src.websockets.binance_client as binance
import src.websockets.coinbase_client as coinbase

# -------------------------------
# CONFIG
# -------------------------------
LOG_DIR = Path("data/logs")
LOG_DIR.mkdir(parents=True, exist_ok=True)

HEALTH_LOG = LOG_DIR / "multi_health.log"
LAT_LOG = LOG_DIR / "latency_comparator.log"

HEARTBEAT_INTERVAL = 60  # seconds
LATENCY_COMPARATOR_INTERVAL = 60  # seconds

LOG_QUEUE_MAXSIZE = 20000
stop_event = asyncio.Event()
log_queue: "asyncio.Queue[tuple[Path, str]]" = asyncio.Queue(maxsize=LOG_QUEUE_MAXSIZE)

metrics = {
    "binance": {"streams": {}, "count": 0, "last_msg": None},
    "coinbase": {"streams": {}, "count": 0, "last_msg": None},
}

# Latest ticker latency windows for comparison
binance_ticker_latencies = deque(maxlen=300)
coinbase_ticker_latencies = deque(maxlen=300)

# -------------------------------
# Shared File Writer
# -------------------------------
async def async_file_writer():
    """Single shared background file writer for all clients."""
    files = {}
    try:
        while not stop_event.is_set() or not log_queue.empty():
            try:
                path, text = await asyncio.wait_for(log_queue.get(), timeout=0.5)
            except asyncio.TimeoutError:
                continue
            if path not in files:
                files[path] = open(path, "a")
            f = files[path]
            f.write(text + "\n")
            f.flush()
            log_queue.task_done()
    finally:
        for f in files.values():
            try:
                f.close()
            except Exception:
                pass


async def enqueue_log(path: Path, text: str):
    """Put log safely into queue."""
    try:
        await log_queue.put((path, text))
    except asyncio.QueueFull:
        print("⚠️  Multi-runner log queue full; dropping log line.")


# -------------------------------
# Heartbeat Monitor
# -------------------------------
async def heartbeat_logger():
    """Log per-minute summary of messages and metrics for both clients."""
    while not stop_event.is_set():
        await asyncio.sleep(HEARTBEAT_INTERVAL)
        summary = {
            "ts": int(time.time() * 1000),
            "binance": {
                "total_msgs": metrics["binance"]["count"],
                "last_msg": metrics["binance"]["last_msg"],
                "streams": metrics["binance"]["streams"],
            },
            "coinbase": {
                "total_msgs": metrics["coinbase"]["count"],
                "last_msg": metrics["coinbase"]["last_msg"],
                "streams": metrics["coinbase"]["streams"],
            },
        }
        await enqueue_log(HEALTH_LOG, json.dumps(summary))
        print(f"[multi-heartbeat] {json.dumps(summary)}")


# -------------------------------
# Shared Latency Comparator
# -------------------------------
async def latency_comparator():
    """Compare ticker latency between Binance and Coinbase every minute."""
    while not stop_event.is_set():
        await asyncio.sleep(LATENCY_COMPARATOR_INTERVAL)

        if binance_ticker_latencies and coinbase_ticker_latencies:
            avg_bin = mean(binance_ticker_latencies)
            avg_cb = mean(coinbase_ticker_latencies)
            gap = avg_cb - avg_bin
            leader = "Binance" if gap > 0 else "Coinbase"
        else:
            avg_bin = avg_cb = gap = None
            leader = None

        record = {
            "timestamp": int(time.time() * 1000),
            "avg_latency_binance_ms": avg_bin,
            "avg_latency_coinbase_ms": avg_cb,
            "avg_gap_ms": gap,
            "leader": leader,
        }

        await enqueue_log(LAT_LOG, json.dumps(record))
        print(f"[latency-comparator] {json.dumps(record)}")


# -------------------------------
# Client Hooks for Comparator
# -------------------------------
def setup_latency_hooks():
    """
    Attach lightweight ticker latency hooks to both clients.
    These capture the per-message latency from each exchange in memory.
    """

    # Wrap their update_metrics or enqueue_log to hook ticker messages
    orig_binance_update = getattr(binance, "update_metrics", None)
    orig_coinbase_update = getattr(coinbase, "update_metrics", None)

    def wrap_binance(stream_name, local_time, latency):
        if stream_name == "ticker":
            binance_ticker_latencies.append(latency)
        if orig_binance_update:
            orig_binance_update(stream_name, local_time, latency)

    def wrap_coinbase(stream_name, local_time, latency):
        if stream_name == "ticker":
            coinbase_ticker_latencies.append(latency)
        if orig_coinbase_update:
            orig_coinbase_update(stream_name, local_time, latency)

    binance.update_metrics = wrap_binance
    coinbase.update_metrics = wrap_coinbase


# -------------------------------
# Run Binance + Coinbase Together
# -------------------------------
async def run_clients():
    setup_latency_hooks()

    writer_task = asyncio.create_task(async_file_writer())
    heartbeat_task = asyncio.create_task(heartbeat_logger())
    comparator_task = asyncio.create_task(latency_comparator())

    # share the same queue and stop_event
    binance.log_queue = log_queue
    coinbase.log_queue = log_queue
    binance.stop_event = stop_event
    coinbase.stop_event = stop_event

    binance_task = asyncio.create_task(binance.main())
    coinbase_task = asyncio.create_task(coinbase.main())

    await stop_event.wait()
    print("Shutdown requested — cancelling clients...")
    binance_task.cancel()
    coinbase_task.cancel()

    await asyncio.gather(binance_task, coinbase_task, return_exceptions=True)

    await log_queue.join()
    writer_task.cancel()
    heartbeat_task.cancel()
    comparator_task.cancel()
    await asyncio.gather(writer_task, heartbeat_task, comparator_task, return_exceptions=True)
    print("✅ Multi-runner shutdown complete.")


def _signal_handler():
    print("Signal received — stopping multi-runner...")
    stop_event.set()


def run():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.add_signal_handler(signal.SIGINT, _signal_handler)
        loop.add_signal_handler(signal.SIGTERM, _signal_handler)
    except NotImplementedError:
        pass

    try:
        loop.run_until_complete(run_clients())
    finally:
        pending = asyncio.all_tasks(loop)
        for task in pending:
            task.cancel()
        loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
        loop.close()


if __name__ == "__main__":
    print("🚀 Starting Multi-Exchange WebSocket Runner (Binance + Coinbase + Latency Comparator)...")
    run()
