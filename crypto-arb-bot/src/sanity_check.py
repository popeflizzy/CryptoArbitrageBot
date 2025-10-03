# src/sanity_check.py
from dotenv import load_dotenv
import os, sys
import ccxt

load_dotenv()   # harmless even if .env absent

print("Python:", sys.version.splitlines()[0])
print("ccxt version:", ccxt.__version__)

# public ticker test (no API keys needed)
exchange = ccxt.binance()
ticker = exchange.fetch_ticker('BTC/USDT')
print("Sample ticker keys:", list(ticker.keys()))
print("Bid:", ticker.get('bid'), "Ask:", ticker.get('ask'))
