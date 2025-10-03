# Crypto Arbitrage Trading Bot

## Purpose
Prototype a Python-based crypto arbitrage bot (paper-trading) across multiple exchanges.

## Week-0: Setup
- Python virtualenv
- Packages installed (see requirements.txt)
- Exchange sandbox accounts created
- .env.example created (do **not** commit secrets)

## How to run (dev)
1. `python -m venv venv && source venv/bin/activate`
2. `pip install -r requirements.txt`
3. Copy `.env.example` -> `.env` and fill keys
4. `python src/sanity_check.py`

#📘 Binance API Rate Limits & Weighting (Spot / REST)

##From Binance Spot API docs:

-Every endpoint has a weight. Some are “cheap” (weight = 1), others are heavier (weight = higher) depending on how much data or complexity. 
Binance Developer Center

-The API responds with headers like X-MBX-USED-WEIGHT-(interval) that tell you how much weight your IP has used in the given time window. 

-If you exceed the limit, you get HTTP 429 (Too Many Requests). If you continue abusing, you can get HTTP 418 — IP ban. The Retry-After header tells you how long to wait. 

-Rate limits are tracked by IP, not by API key (for many endpoints). 


-Orders have a special “unfilled orders” rate limit: placing too many new orders that remain unfilled can get you blocked. But filled orders reduce that counter. 


-There was a recent update (Nov 2023) increasing Binance’s spot API order rate limit: from 50 orders / 10 seconds and 160,000 / 24 hours up to 100 / 10 seconds and 200,000 / 24 hours. 


#🔐 Authentication / API Keys / Signing

-Some endpoints are public (market data) — no API key or signing needed. For example: fetch_ticker, depth, trades. 


-Other endpoints are private / signed (account info, placing orders). Those require authentication. 

-Binance supports several key types: Ed25519 (recommended), HMAC-SHA256, and RSA keys. Ed25519 is faster and provides performance/security benefits. 

-For signed requests, you send X-MBX-APIKEY as HTTP header. Then the request parameters + timestamp are signed with your secret key using HMAC-SHA256 (or appropriate algorithm depending on key type). 

-In Spot API, each endpoint has a “security type” (e.g. NONE, SIGNED) — you must check this in docs to know if signing is needed. 

-Also, you must pay attention to recvWindow (time window tolerance between your timestamp and server time). Some requests may be rejected if timestamp is too far from server’s time. 
