# src/websockets/coinbase_client.py
"""
Production-ready Coinbase WebSocket client for BTC-USD.

Features:
- Subscribes to matches (trades), ticker, and level2 (orderbook).
- Exponential backoff + jitter on reconnect.
- Centralized async file writer (avoids blocking event loop).
- Per-stream metrics and a minute-level heartbeat health log.
- Graceful shutdown on SIGINT/SIGTERM.
- ISO-8601 timestamp parsing to epoch-ms for accurate latency.
"""

import asyncio
import json
import signal
import time
from pathlib import Path
from random import uniform
from typing import Any, Dict, Tuple

import websockets  # pip install websockets
from datetime import datetime, timezone

# -------------------------
# CONFIG
# -------------------------
COINBASE_WS_URL = "wss://ws-feed.exchange.coinbase.com"
PRODUCT_ID = "BTC-USD"  # Coinbase uses BTC-USD format

# Logging paths
LOG_DIR = Path("data/logs")
LOG_DIR.mkdir(parents=True, exist_ok=True)
TRADE_LOG = LOG_DIR / "coinbase_trades.log"
TICKER_LOG = LOG_DIR / "coinbase_ticker.log"
DEPTH_LOG = LOG_DIR / "coinbase_orderbook.log"
HEALTH_LOG = LOG_DIR / "coinbase_health.log"

# Backoff and connection tuning
MAX_BACKOFF = 30  # seconds
PING_INTERVAL = 20
PING_TIMEOUT = 20
SUBSCRIBE_RATE_LIMIT_SECONDS = 1.0

# Heartbeat / health
HEARTBEAT_INTERVAL = 60  # seconds

# Writer queue size
LOG_QUEUE_MAXSIZE = 10000

# -------------------------
# GLOBALS / METRICS
# -------------------------
stop_event = asyncio.Event()

metrics: Dict[str, Dict[str, Any]] = {
    "trades": {"count": 0, "last_local_time": None, "latency_sum": 0},
    "ticker": {"count": 0, "last_local_time": None, "latency_sum": 0},
    "orderbook": {"count": 0, "last_local_time": None, "latency_sum": 0},
}

log_queue: "asyncio.Queue[Tuple[Path, str]]" = asyncio.Queue(maxsize=LOG_QUEUE_MAXSIZE)


# -------------------------
# UTILITIES
# -------------------------
def now_ms() -> int:
    return int(time.time() * 1000)


def iso_to_epoch_ms(s: str) -> int:
    """
    Parse ISO-8601 timestamp (e.g. '2025-10-24T08:12:34.567Z') to epoch ms.
    Falls back to current time if parsing fails.
    """
    if s is None:
        return now_ms()
    try:
        # handle trailing Z (Zulu)
        if s.endswith("Z"):
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        else:
            dt = datetime.fromisoformat(s)
        epoch_ms = int(dt.timestamp() * 1000)
        return epoch_ms
    except Exception:
        # best-effort fallback
        return now_ms()


async def async_file_writer():
    """Background task that writes queued lines to disk (one writer for all logs)."""
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
    """Put a log line into the queue without blocking forever."""
    try:
        await log_queue.put((path, text))
    except asyncio.QueueFull:
        print("⚠️  Log queue full; dropping log line.")


def format_entry(stream_name: str, local_time: int, event_time: int, latency: int, data: dict) -> str:
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
    delay += uniform(0, 1)
    await asyncio.sleep(delay)


async def subscribe(ws, channels: list):
    """Helper to send the subscribe message (Coinbase format)."""
    sub = {"type": "subscribe", "product_ids": [PRODUCT_ID], "channels": channels}
    await ws.send(json.dumps(sub))


async def handle_stream(stream_name: str, channels_spec: list, log_path: Path):
    """
    channels_spec is a list of dicts following Coinbase channel spec,
    e.g. [{"name": "matches"}, {"name":"ticker"}, {"name":"level2"}]
    """
    attempt = 0
    last_subscribe_ts = 0.0

    while not stop_event.is_set():
        try:
            async with websockets.connect(COINBASE_WS_URL, ping_interval=PING_INTERVAL, ping_timeout=PING_TIMEOUT) as ws:
                # rate limit subscribe calls
                now_t = time.time()
                since = now_t - last_subscribe_ts
                if since < SUBSCRIBE_RATE_LIMIT_SECONDS:
                    await asyncio.sleep(SUBSCRIBE_RATE_LIMIT_SECONDS - since)

                await subscribe(ws, channels_spec)
                last_subscribe_ts = time.time()
                print(f"✅ Connected & subscribed to Coinbase channels -> {channels_spec}")
                attempt = 0

                async for raw in ws:
                    if stop_event.is_set():
                        break

                    try:
                        data = json.loads(raw)
                    except Exception:
                        continue

                    # ignore subscription ack / heartbeat types we don't need
                    if data.get("type") in ("subscriptions",):
                        continue

                    # Coinbase message timestamp is usually in field 'time' (ISO string)
                    ts_field = data.get("time") or data.get("timestamp")
                    event_time_ms = iso_to_epoch_ms(ts_field) if ts_field else now_ms()

                    local = now_ms()
                    latency = local - event_time_ms if event_time_ms is not None else 0

                    # log entry
                    entry_text = format_entry(stream_name, local, int(event_time_ms), int(latency), data)
                    await enqueue_log(log_path, entry_text)

                    # update metrics (stream_name categories: trades, ticker, orderbook)
                    update_metrics(stream_name, local, int(latency))

        except asyncio.CancelledError:
            raise
        except Exception as exc:
            attempt += 1
            print(f"⚠️  {stream_name} disconnected (attempt={attempt}): {exc}")
            await exponential_backoff(attempt)
            continue

    print(f"🛑 Exiting Coinbase handler for {stream_name}")


# -------------------------
# DRIVER
# -------------------------
async def main():
    writer_task = asyncio.create_task(async_file_writer())
    heartbeat_task = asyncio.create_task(heartbeat_logger())

    # We create three handlers but each subscribes to the channel group we want.
    # Simpler model: keep separate handlers so one failing doesn't kill others.
    streams = [
        ("trades", [{"name": "matches"}], TRADE_LOG),
        ("ticker", [{"name": "ticker"}], TICKER_LOG),
        ("orderbook", [{"name": "level2"}], DEPTH_LOG),
    ]

    handler_tasks = [asyncio.create_task(handle_stream(name, channels, path)) for name, channels, path in streams]

    await stop_event.wait()
    print("Shutdown requested — cancelling Coinbase stream handlers...")

    for t in handler_tasks:
        t.cancel()
    await asyncio.gather(*handler_tasks, return_exceptions=True)

    await log_queue.join()
    writer_task.cancel()
    heartbeat_task.cancel()
    await asyncio.gather(writer_task, heartbeat_task, return_exceptions=True)
    print("Shutdown complete.")


def _signal_handler():
    print("Signal received — stopping...")
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
        loop.run_until_complete(main())
    finally:
        pending = asyncio.all_tasks(loop)
        for task in pending:
            task.cancel()
        loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
        loop.close()


if __name__ == "__main__":
    print("Starting Coinbase WebSocket client (matches, ticker, level2)...")
    run()
