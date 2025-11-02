import os
import csv
import asyncio
from datetime import datetime, timezone
from typing import Optional

# Config defaults (tweak when calling)
DEFAULT_INTERVAL = 0.5         # seconds between checks
DEFAULT_THRESHOLD = 0.001      # decimal fraction: 0.001 == 0.1% net profit threshold
DEFAULT_FEE_BUY = 0.001        # fee when buying on exchange (0.001 == 0.1%)
DEFAULT_FEE_SELL = 0.001       # fee when selling on exchange

LOG_DIR = os.path.join("logs")
LOG_PREFIX = "arbitrage"


def _ensure_log_dir():
    if not os.path.exists(LOG_DIR):
        os.makedirs(LOG_DIR, exist_ok=True)


async def _append_csv_row(filepath: str, row: list, header: Optional[list] = None):
    """
    Append a row to CSV using a thread to avoid blocking the event loop.
    If file doesn't exist and header is provided, writes header first.
    """
    def _write():
        exists = os.path.exists(filepath)
        with open(filepath, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            if (not exists) and header:
                writer.writerow(header)
            writer.writerow(row)

    await asyncio.to_thread(_write)


async def arbitrage_engine(
    obm,
    interval: float = DEFAULT_INTERVAL,
    threshold: float = DEFAULT_THRESHOLD,
    fee_buy: float = DEFAULT_FEE_BUY,
    fee_sell: float = DEFAULT_FEE_SELL,
    logfile: Optional[str] = None,
):
    """
    Continuously inspect OrderBookManager (obm) for cross-exchange arbitrage opportunities.

    - obm: OrderBookManager instance (must have .books dict and ._lock asyncio.Lock)
    - interval: seconds between checks
    - threshold: decimal fraction for minimum net profit (e.g. 0.001 == 0.1%)
    - fee_buy / fee_sell: decimal fractions representing fees to apply
    - logfile: optional path; if None writes to ./logs/arbitrage_{YYYYmmdd}.csv

    Normalized message schema (what obm stores per exchange):
    {
        "bids": [[price, size], ...],
        "asks": [[price, size], ...],
        "best_bid": float,
        "best_ask": float,
        "timestamp": ISO-str
    }
    """

    # prepare logfile path
    _ensure_log_dir()
    if logfile is None:
        date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
        logfile = os.path.join(LOG_DIR, f"{LOG_PREFIX}_{date_str}.csv")

    header = [
        "ts_utc",
        "buy_exchange",
        "sell_exchange",
        "buy_price",
        "sell_price",
        "gross_spread",
        "net_spread",
        "profit_pct_decimal",
        "fee_buy",
        "fee_sell",
        "obm_ts_buy",
        "obm_ts_sell",
    ]

    print(f"[arb] Engine started | interval={interval}s threshold={threshold*100:.4f}% fees(buy/sell)={fee_buy*100:.4f}%/{fee_sell*100:.4f}% logfile={logfile}")

    try:
        while True:
            await asyncio.sleep(interval)

            # copy books snapshot safely
            async with obm._lock:
                books_snapshot = {k: dict(v) for k, v in obm.books.items()}

            # need at least two exchanges to compare
            exchanges = list(books_snapshot.keys())
            if len(exchanges) < 2:
                # nothing to do yet
                continue

            # build list of valid top-of-book prices
            valid = {}
            for ex, d in books_snapshot.items():
                bid = d.get("best_bid")
                ask = d.get("best_ask")
                ts = d.get("timestamp")
                if isinstance(bid, (int, float)) and isinstance(ask, (int, float)):
                    valid[ex] = {"best_bid": float(bid), "best_ask": float(ask), "timestamp": ts}

            # compare all pairs: sell on A (use best_bid), buy on B (use best_ask)
            opportunities = []
            for sell_ex, sell_data in valid.items():
                for buy_ex, buy_data in valid.items():
                    if sell_ex == buy_ex:
                        continue

                    sell_price = sell_data["best_bid"]
                    buy_price = buy_data["best_ask"]

                    # gross spread (sell_price - buy_price)
                    gross_spread = sell_price - buy_price

                    # apply fees: when buying you pay buy_price*(1 + fee_buy), when selling you receive sell_price*(1 - fee_sell)
                    net_receive = sell_price * (1 - fee_sell)
                    net_cost = buy_price * (1 + fee_buy)
                    net_spread = net_receive - net_cost

                    # profit percent relative to cost
                    profit_pct = (net_spread / net_cost) if net_cost != 0 else 0.0

                    if profit_pct >= threshold:
                        opportunities.append({
                            "sell_ex": sell_ex,
                            "buy_ex": buy_ex,
                            "sell_price": sell_price,
                            "buy_price": buy_price,
                            "gross_spread": gross_spread,
                            "net_spread": net_spread,
                            "profit_pct": profit_pct,
                            "ts_sell": sell_data.get("timestamp"),
                            "ts_buy": buy_data.get("timestamp"),
                        })

            # if any opportunities found, log them and print a compact alert
            if opportunities:
                now_ts = datetime.now(timezone.utc).isoformat()
                for opp in opportunities:
                    # print compact alert
                    print(
                        f"[arb] {now_ts} SELL on {opp['sell_ex']} @ {opp['sell_price']:.2f} | "
                        f"BUY on {opp['buy_ex']} @ {opp['buy_price']:.2f} | "
                        f"net_spread={opp['net_spread']:.2f} profit_pct={opp['profit_pct']*100:.4f}%"
                    )

                    # append csv row (offload blocking IO)
                    row = [
                        now_ts,
                        opp["buy_ex"],
                        opp["sell_ex"],
                        f"{opp['buy_price']:.8f}",
                        f"{opp['sell_price']:.8f}",
                        f"{opp['gross_spread']:.8f}",
                        f"{opp['net_spread']:.8f}",
                        f"{opp['profit_pct']:.8f}",
                        f"{fee_buy:.8f}",
                        f"{fee_sell:.8f}",
                        opp.get("ts_buy"),
                        opp.get("ts_sell"),
                    ]
                    await _append_csv_row(logfile, row, header=header)

    except asyncio.CancelledError:
        # graceful shutdown when task is cancelled
        print("[arb] Cancelled — stopping arbitrage engine.")
        return
    except Exception as e:
        # log unexpected exceptions but don't crash silently
        print(f"[arb] Unexpected error in arbitrage engine: {e}")
        raise
