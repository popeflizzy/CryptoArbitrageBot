"""
multi_runner.py
----------------
Runs Binance + Coinbase WebSocket clients concurrently.
Logs health metrics, tracks latency, and saves unified data streams to /data/logs.
"""

import asyncio
import os
import sys
from datetime import datetime, timezone
from collections import deque
from pathlib import Path

# Local imports
from src.websockets.binance_client import run_binance
from src.websockets.coinbase_client import run_coinbase


# ============================================================
# CONFIG
# ============================================================
LOG_DIR = Path("data/logs")
LOG_DIR.mkdir(parents=True, exist_ok=True)
MAX_LATENCY_SAMPLES = 50
RECONNECT_DELAY = 3


# ============================================================
# FIXED ASYNC FILE WRITER
# ============================================================
async def file_writer(queue, log_dir):
    """
    Asynchronously writes messages from queue to files without using async file handles.
    Thread-safe for asyncio loops (uses asyncio.to_thread for blocking I/O).
    """
    os.makedirs(log_dir, exist_ok=True)

    def _write_to_file(path, text):
        with open(path, "a", encoding="utf-8") as f:
            f.write(text + "\n")

    while True:
        try:
            msg = await queue.get()
            if msg is None:
                break
            ts = datetime.now(timezone.utc).isoformat()
            log_path = os.path.join(log_dir, "multi_health.log")
            await asyncio.to_thread(_write_to_file, log_path, f"[{ts}] {msg}")
            queue.task_done()
        except Exception as e:
            print(f"[writer-error] {e}")
            await asyncio.sleep(1)


# ============================================================
# LATENCY COMPARATOR
# ============================================================
class SharedLatencyComparator:
    def __init__(self, max_samples=MAX_LATENCY_SAMPLES):
        self.latency_buffer = {"binance": deque(maxlen=max_samples), "coinbase": deque(maxlen=max_samples)}

    def record(self, source, latency):
        self.latency_buffer[source].append(latency)

    def avg_latency(self, source):
        buf = self.latency_buffer[source]
        return sum(buf) / len(buf) if buf else None

    def summary(self):
        b = self.avg_latency("binance")
        c = self.avg_latency("coinbase")
        if b and c:
            diff = abs(b - c)
            return f"[latency-summary] Binance={b:.3f}s | Coinbase={c:.3f}s | Δ={diff:.3f}s"
        return "[latency-summary] waiting for enough samples..."


# ============================================================
# CLIENT WRAPPERS
# ============================================================
async def run_client(name, runner_func, log_queue, comparator):
    """
    Wraps the run_* websocket client (e.g., Binance/Coinbase) with reconnect + error handling.
    Each runner_func must yield tuples (timestamp_received, latency_ms)
    """
    while True:
        try:
            print(f"[{name}] Connecting...")
            async for ts_recv, latency in runner_func():
                latency_sec = latency / 1000.0
                comparator.record(name, latency_sec)
                await log_queue.put(f"[{name}] tick latency={latency_sec:.3f}s at {ts_recv}")
        except Exception as e:
            err_msg = f"[{name}] Error: {e}, reconnecting in {RECONNECT_DELAY}s..."
            print(err_msg)
            await log_queue.put(err_msg)
            await asyncio.sleep(RECONNECT_DELAY)


# ============================================================
# MONITOR + MAIN LOOP
# ============================================================
async def monitor_health(log_queue, comparator):
    while True:
        summary = comparator.summary()
        print(summary)
        await log_queue.put(summary)
        await asyncio.sleep(5)


async def main():
    print("Starting multi_runner (Binance + Coinbase + comparator)...")

    log_queue = asyncio.Queue()
    comparator = SharedLatencyComparator()

    # Start file writer
    writer_task = asyncio.create_task(file_writer(log_queue, LOG_DIR))

    # Start exchange clients
    binance_task = asyncio.create_task(run_client("binance", run_binance, log_queue, comparator))
    coinbase_task = asyncio.create_task(run_client("coinbase", run_coinbase, log_queue, comparator))

    # Start health monitor
    monitor_task = asyncio.create_task(monitor_health(log_queue, comparator))

    await asyncio.gather(binance_task, coinbase_task, monitor_task, writer_task)


def run():
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[EXIT] Graceful shutdown...")


if __name__ == "__main__":
    run()
