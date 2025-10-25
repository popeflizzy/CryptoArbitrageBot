# src/core/orderbook_manager.py
"""
Orderbook Manager

- Keeps an in-memory top-N orderbook per exchange (Binance, Coinbase).
- Exposes process_message(exchange, raw_data) which accepts parsed JSON messages
  from each exchange's orderbook/depth stream.
- Computes cross-exchange spreads and logs to a file via the provided enqueue_log
  function (non-blocking).
- Thread/async-safe because it only uses asyncio and is expected to be called
  from the same event loop as the websocket clients (as we do in multi_runner).
"""

from collections import defaultdict, OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple, Callable, Optional
import json
import math
import time

LOG_PATH = Path("data/logs/spread_monitor.log")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

# Type for the enqueue function you will pass in (from multi_runner or clients)
EnqueueLogType = Callable[[Path, str], None]

DEFAULT_TOP_N = 10


@dataclass
class Level:
    price: float
    size: float


class SimpleOrderBook:
    """
    Maintain a price->size mapping and provide top N bids/asks.
    Bids sorted descending, asks ascending.
    """

    def __init__(self):
        self.bids: Dict[float, float] = {}  # price -> size
        self.asks: Dict[float, float] = {}

    def apply_update(self, side: str, price: float, size: float):
        if size == 0 or math.isclose(size, 0.0):
            # delete level if present
            if side == "buy":
                self.bids.pop(price, None)
            else:
                self.asks.pop(price, None)
        else:
            if side == "buy":
                self.bids[price] = size
            else:
                self.asks[price] = size

    def top_n(self, n: int = DEFAULT_TOP_N) -> Tuple[List[Level], List[Level]]:
        top_bids = sorted(self.bids.items(), key=lambda x: -x[0])[:n]
        top_asks = sorted(self.asks.items(), key=lambda x: x[0])[:n]
        return ([Level(p, q) for p, q in top_bids], [Level(p, q) for p, q in top_asks])

    def best_bid(self) -> Optional[Level]:
        if not self.bids:
            return None
        p = max(self.bids.keys())
        return Level(p, self.bids[p])

    def best_ask(self) -> Optional[Level]:
        if not self.asks:
            return None
        p = min(self.asks.keys())
        return Level(p, self.asks[p])


class OrderbookManager:
    def __init__(self, enqueue_log: Optional[EnqueueLogType] = None, top_n: int = DEFAULT_TOP_N):
        # per-exchange orderbooks
        self.orderbooks: Dict[str, SimpleOrderBook] = {
            "binance": SimpleOrderBook(),
            "coinbase": SimpleOrderBook(),
        }
        # optional external log function (e.g. multi_runner.enqueue_log)
        self.enqueue_log = enqueue_log
        self.top_n = top_n

    # ---------- Public API ----------
    def set_enqueue_log(self, fn: EnqueueLogType):
        """Set the async enqueue_log function from multi_runner so manager can log."""
        self.enqueue_log = fn

    def get_snapshot(self, exchange: str, n: int = None) -> Dict[str, List[Dict]]:
        """Return top-n bids and asks for an exchange as lists of dicts."""
        n = n or self.top_n
        ob = self.orderbooks.get(exchange)
        if ob is None:
            return {"bids": [], "asks": []}
        bids, asks = ob.top_n(n)
        return {
            "bids": [{"price": l.price, "size": l.size} for l in bids],
            "asks": [{"price": l.price, "size": l.size} for l in asks],
        }

    def process_message(self, exchange: str, data: dict):
        """
        Main entry point.
        - `exchange` should be 'binance' or 'coinbase'
        - `data` is the parsed JSON payload from the websocket handler
        This method tolerates different message shapes:
          - Binance depthUpdate: {'b': [['price','qty']], 'a': [...] }
          - Binance snapshot (if you choose to fetch): similar shape
          - Coinbase l2update: {'changes': [['buy','price','size']] }
          - Coinbase snapshot: {'bids': [...], 'asks': [...]}
        After applying the update(s), it computes cross-exchange spreads and logs them.
        """
        ex = exchange.lower()
        if ex not in self.orderbooks:
            # ignore unknown exchanges
            return

        ob = self.orderbooks[ex]

        # --- Binance handling ---
        # Binance incremental depth update fields: 'b' (bids), 'a' (asks) as lists of [price, qty]
        if ex == "binance":
            # Binance incremental update
            # Accept multiple formats defensively
            if "b" in data or "a" in data:
                bids = data.get("b", [])
                asks = data.get("a", [])
                for p_str, q_str in bids:
                    try:
                        p = float(p_str)
                        q = float(q_str)
                        ob.apply_update("buy", p, q)
                    except Exception:
                        continue
                for p_str, q_str in asks:
                    try:
                        p = float(p_str)
                        q = float(q_str)
                        ob.apply_update("sell", p, q)
                    except Exception:
                        continue
            # Binance sometimes uses 'U','u' or other metadata; we ignore those here.

        # --- Coinbase handling ---
        # Coinbase l2update: {"changes": [["buy","price","size"], ...], ...}
        elif ex == "coinbase":
            if data.get("type") == "snapshot":
                # snapshot contains 'bids' and 'asks' as lists
                bids = data.get("bids", [])
                asks = data.get("asks", [])
                # replace local book (simple strategy: clear and insert)
                ob.bids.clear()
                ob.asks.clear()
                for p_str, q_str in bids:
                    try:
                        p = float(p_str)
                        q = float(q_str)
                        ob.apply_update("buy", p, q)
                    except Exception:
                        continue
                for p_str, q_str in asks:
                    try:
                        p = float(p_str)
                        q = float(q_str)
                        ob.apply_update("sell", p, q)
                    except Exception:
                        continue
            elif "changes" in data:
                changes = data.get("changes", [])
                for change in changes:
                    try:
                        side, p_str, q_str = change
                        p = float(p_str)
                        q = float(q_str)
                        if side.lower() in ("buy", "b"):
                            ob.apply_update("buy", p, q)
                        else:
                            ob.apply_update("sell", p, q)
                    except Exception:
                        continue

        # After applying updates, compute cross spreads and log
        self._compute_and_log_spread()

    # ---------- Internal ----------
    def _compute_and_log_spread(self):
        b_ob = self.orderbooks["binance"]
        c_ob = self.orderbooks["coinbase"]

        b_best_bid = b_ob.best_bid()
        b_best_ask = b_ob.best_ask()
        c_best_bid = c_ob.best_bid()
        c_best_ask = c_ob.best_ask()

        ts = int(time.time() * 1000)

        record = {
            "ts": ts,
            "binance": {
                "best_bid": (b_best_bid.price if b_best_bid else None),
                "best_bid_size": (b_best_bid.size if b_best_bid else None),
                "best_ask": (b_best_ask.price if b_best_ask else None),
                "best_ask_size": (b_best_ask.size if b_best_ask else None),
            },
            "coinbase": {
                "best_bid": (c_best_bid.price if c_best_bid else None),
                "best_bid_size": (c_best_bid.size if c_best_bid else None),
                "best_ask": (c_best_ask.price if c_best_ask else None),
                "best_ask_size": (c_best_ask.size if c_best_ask else None),
            },
            # cross spreads
            "spread_binance_bid_vs_coinbase_ask": None,
            "spread_coinbase_bid_vs_binance_ask": None,
        }

        # if both exist compute spreads
        if b_best_bid and c_best_ask:
            record["spread_binance_bid_vs_coinbase_ask"] = round(b_best_bid.price - c_best_ask.price, 8)
        if c_best_bid and b_best_ask:
            record["spread_coinbase_bid_vs_binance_ask"] = round(c_best_bid.price - b_best_ask.price, 8)

        # attach a textual signal if opportunity apparent (simple threshold)
        # e.g., if spread > 0.5 USD or relative > some basis points you may treat as signal
        # But here we only annotate the sign:
        if record["spread_binance_bid_vs_coinbase_ask"] is not None and record["spread_binance_bid_vs_coinbase_ask"] > 0:
            record["signal_binance_bid_sell_coinbase_ask"] = True
        else:
            record["signal_binance_bid_sell_coinbase_ask"] = False

        if record["spread_coinbase_bid_vs_binance_ask"] is not None and record["spread_coinbase_bid_vs_binance_ask"] > 0:
            record["signal_coinbase_bid_sell_binance_ask"] = True
        else:
            record["signal_coinbase_bid_sell_binance_ask"] = False

        # write record to log (if enqueue function is set use it; otherwise fallback to direct write)
        line = json.dumps(record, separators=(",", ":"))
        if self.enqueue_log:
            try:
                # allow both sync and async enqueue_log (multi_runner's is async)
                self.enqueue_log(LOG_PATH, line)
            except TypeError:
                # maybe an awaitable (async function) - schedule it
                import asyncio
                asyncio.create_task(self.enqueue_log(LOG_PATH, line))
            except Exception:
                # fallback to direct write
                with open(LOG_PATH, "a") as f:
                    f.write(line + "\n")
        else:
            # direct write fallback
            with open(LOG_PATH, "a") as f:
                f.write(line + "\n")

    # convenience utility
    def snapshot_all(self, n: int = None) -> Dict[str, Dict]:
        return {
            ex: self.get_snapshot(ex, n)
            for ex in self.orderbooks.keys()
        }


# Single global manager instance (importers can reuse)
manager = OrderbookManager()
