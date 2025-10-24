# src/websockets/binance_client.py
"""
Production-ready Binance WebSocket client for BTCUSDT.

Features:
- Subscribes to trades, bookTicker (ticker), and depth (orderbook).
- Exponential backoff + jitter on reconnect.
- Centralized async file writer (avoids blocking event loop).
- Per-stream metrics and a minute-level heartbeat health log.
- Graceful shutdown on SIGINT/SIGTERM.
- All improvements included up-front to avoid repeated rewrites.

Dependencies:
- websockets  (install into your venv: pip install websockets)
"""

import asyncio
import json
import signal
import time
from pathlib import Path
from random import uniform
from typing import Any, Dict, Tuple

import websockets  # pip install websockets

# -------------------------
# CONFIG
# -------------------------
BINANCE_WS_URL = "wss://stream.binance.com:9443/ws"
SYMBOL = "btcusdt"

# Logging paths
LOG_DIR = Path("data/logs")
LOG_DIR.mkdir(parents=True, exist_ok=True)
TRADE_LOG = LOG_DIR / "binance_trades.log"
TICKER_LOG = LOG_DIR / "binance_ticker.log"
DEPTH_LOG = LOG_DIR / "binance_orderbook.log"
HEALTH_LOG = LOG_DIR / "binance_health.log"

# Backoff and connection tuning
MAX_BACKOFF = 30  # max seconds for exponential backoff
PING_INTERVAL = 20  # seconds (websockets ping)
PING_TIMEOUT = 20
SUBSCRIBE_RATE_LIMIT_SECONDS = 1.0  # don't spam subscribe messages (safety)

# Heartbeat / health
HEARTBEAT_INTERVAL = 60  # seconds -- write a heartbeat/metrics line every minute

# Writer queue sizes
LOG_QUEUE_MAXSIZE = 10000

# -------------------------
# GLOBALS / METRICS
# -------------------------
stop_event = asyncio.Event()

# metrics: dict(stream_name -> metrics)
metrics: Dict[str, Dict[str, Any]] = {
    "trades": {"count": 0, "last_local_time": None, "latency_sum": 0},
    "ticker": {"count": 0, "last_local_time": None, "latency_sum": 0},
    "orderbook": {"count": 0, "last_local_time": None, "latency_sum": 0},
}

# central async queue for writes: items are tuples (Path, text)
log_queue: "asyncio.Queue[Tuple[Path, str]]" = asyncio.Queue(maxsize=LOG_QUEUE_MAXSIZE)


# -------------------------
# UTILITIES
# -------------------------
def now_ms() -> int:
    return int(time.time() * 1000)


async def async_file_writer():
    """Background task that writes queued lines to disk (one writer for all logs)."""
    # Use file handles kept open to reduce overhead
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
        # close file handles
        for f in files.values():
            try:
                f.close()
            except Exception:
                pass


async def enqueue_log(path: Path, text: str):
    """Put a log line into the queue without blocking forever."""
    try:
        await log_queue.put((path, text))
    except asyncio.QueueFull:
        # In extremely rare cases drop the log (or consider backpressure)
        print("⚠️  Log queue full; dropping log line.")


def format_entry(stream_name: str, local_time: int, event_time: int, latency: int, data: dict) -> str:
    """Return a compact JSON string for writing to logs."""
    entry = {
        "type": stream_name,
        "local_time": local_time,
        "event_time": event_time,
        "latency_ms": latency,
        "data": data,
    }
    return json.dumps(entry, separators=(",", ":"))


def update_metrics(stream_name: str, local_time: int, latency: int):
    m = metrics.get(stream_name)
    if m is None:
        return
    m["count"] += 1
    m["last_local_time"] = local_time
    m["latency_sum"] += latency if latency is not None else 0


async def heartbeat_logger():
    """Writes a summary health line to HEALTH_LOG every HEARTBEAT_INTERVAL seconds."""
    while not stop_event.is_set():
        await asyncio.sleep(HEARTBEAT_INTERVAL)
        summary = {
            "ts": now_ms(),
            "streams": {
                name: {
                    "count": metrics[name]["count"],
                    "last_local_time": metrics[name]["last_local_time"],
                    "avg_latency_ms": (metrics[name]["latency_sum"] / metrics[name]["count"])
                    if metrics[name]["count"]
                    else None,
                }
                for name in metrics
            },
        }
        line = json.dumps(summary)
        await enqueue_log(HEALTH_LOG, line)
        print(f"[heartbeat] {line}")


# -------------------------
# RECONNECT / STREAM HANDLER
# -------------------------
async def exponential_backoff(attempt: int):
    delay = min(MAX_BACKOFF, 2 ** attempt)
    delay += uniform(0, 1)  # jitter
    await asyncio.sleep(delay)


async def handle_stream(stream_name: str, params: list, log_path: Path):
    """
    Maintains a persistent websocket for a specific stream (trade/ticker/orderbook).
    Each stream has its own reconnect/backoff loop so one stream failing doesn't kill others.
    """
    attempt = 0
    last_subscribe_ts = 0.0

    while not stop_event.is_set():
        try:
            async with websockets.connect(
                BINANCE_WS_URL, ping_interval=PING_INTERVAL, ping_timeout=PING_TIMEOUT
            ) as ws:
                # subscribe (respect a minimal rate limit)
                now_t = time.time()
                since = now_t - last_subscribe_ts
                if since < SUBSCRIBE_RATE_LIMIT_SECONDS:
                    await asyncio.sleep(SUBSCRIBE_RATE_LIMIT_SECONDS - since)

                sub_msg = {"method": "SUBSCRIBE", "params": params, "id": 1}
                await ws.send(json.dumps(sub_msg))
                last_subscribe_ts = time.time()
                print(f"✅ Connected & subscribed to {stream_name} -> {params}")

                attempt = 0  # reset backoff attempts on success

                async for raw in ws:
                    if stop_event.is_set():
                        break

                    try:
                        data = json.loads(raw)
                    except Exception:
                        # non-json messages — ignore
                        continue

                    # Skip subscription ack messages
                    if "result" in data:
                        continue

                    local = now_ms()
                    # event_time can be 'E' (eventTime ms) or 'T' (tradeTime ms) depending on payload
                    event_time = data.get("E") or data.get("T")

                    # If no event timestamp (bookTicker), use local time as proxy and latency 0
                    if event_time is None:
                        event_time = local
                        latency = 0
                    else:
                        latency = local - int(event_time)

                    # log entry
                    entry_text = format_entry(stream_name, local, int(event_time), latency, data)
                    await enqueue_log(log_path, entry_text)

                    # update metrics
                    update_metrics(stream_name, local, latency)

        except asyncio.CancelledError:
            # allow cancellation to propagate for graceful shutdown
            raise
        except Exception as exc:
            attempt += 1
            print(f"⚠️  {stream_name} disconnected (attempt={attempt}): {exc}")
            # Backoff before reconnecting
            await exponential_backoff(attempt)
            continue

    print(f"🛑 Exiting handler for {stream_name}")


# -------------------------
# RUN / SHUTDOWN
# -------------------------
async def main():
    # Start background file writer and heartbeat logger
    writer_task = asyncio.create_task(async_file_writer())
    heartbeat_task = asyncio.create_task(heartbeat_logger())

    streams = [
        ("trades", [f"{SYMBOL}@trade"], TRADE_LOG),
        ("ticker", [f"{SYMBOL}@bookTicker"], TICKER_LOG),
        ("orderbook", [f"{SYMBOL}@depth@100ms"], DEPTH_LOG),
    ]

    handler_tasks = [asyncio.create_task(handle_stream(name, params, path)) for name, params, path in streams]

    # Wait for stop_event then gracefully cancel
    await stop_event.wait()
    print("Shutdown requested — cancelling stream handlers...")

    for t in handler_tasks:
        t.cancel()
    # Wait for them to finish
    await asyncio.gather(*handler_tasks, return_exceptions=True)

    # Ensure all queued logs are flushed
    await log_queue.join()
    # Stop writer and heartbeat
    writer_task.cancel()
    heartbeat_task.cancel()
    await asyncio.gather(writer_task, heartbeat_task, return_exceptions=True)
    print("Shutdown complete.")


def _signal_handler():
    print("Signal received — stopping...")
    stop_event.set()


def run():
    """Entry point — creates a fresh event loop safely for modern Python versions."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    # Attach signal handlers if supported
    try:
        loop.add_signal_handler(signal.SIGINT, _signal_handler)
        loop.add_signal_handler(signal.SIGTERM, _signal_handler)
    except NotImplementedError:
        # Not supported on Windows' default event loop, safe to ignore
        pass

    try:
        loop.run_until_complete(main())
    finally:
        # Graceful teardown
        pending = asyncio.all_tasks(loop)
        for task in pending:
            task.cancel()
        loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
        loop.close()


if __name__ == "__main__":
    print("Starting Binance WebSocket client (trades, ticker, orderbook)...")
    run()
