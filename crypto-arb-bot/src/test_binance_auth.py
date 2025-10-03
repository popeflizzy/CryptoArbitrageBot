# src/test_binance_auth.py
import os
from dotenv import load_dotenv
import ccxt

# Load .env file
load_dotenv()

api_key = os.getenv("BINANCE_API_KEY")
api_secret = os.getenv("BINANCE_API_SECRET")

print("API key loaded:", bool(api_key))
print("Secret loaded:", bool(api_secret))

# Initialize Binance testnet client
binance = ccxt.binance({
    "apiKey": api_key,
    "secret": api_secret,
    "enableRateLimit": True,
})
binance.set_sandbox_mode(True)  # important: ensure testnet mode

# Try fetching account info
try:
    balance = binance.fetch_balance()
    print("✅ Connected! Balance keys:", list(balance.keys())[:5])
except Exception as e:
    print("❌ Error:", str(e))
