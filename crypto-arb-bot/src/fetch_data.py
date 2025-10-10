import ccxt
import json
import os
from datetime import datetime

# Make sure data folder exists
os.makedirs("data", exist_ok=True)

# Initialize exchange
exchange = ccxt.binance({
    "enableRateLimit": True
})

pair = "BTC/USDT"

# Fetch live data
ticker = exchange.fetch_ticker(pair)
orderbook = exchange.fetch_order_book(pair, limit=10)
trades = exchange.fetch_trades(pair, limit=5)

# Combine into one dictionary
data = {
    "timestamp": datetime.utcnow().isoformat(),
    "pair": pair,
    "ticker": ticker,
    "orderbook": orderbook,
    "recent_trades": trades
}

# Save to JSON file
filename = f"data/{pair.replace('/', '_')}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
with open(filename, "w") as f:
    json.dump(data, f, indent=2)

print(f"✅ Data saved to {filename}")
