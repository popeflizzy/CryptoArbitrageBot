[README.md](https://github.com/user-attachments/files/22883452/README.md)
# 🧠 Crypto Arbitrage Trading Bot (Internship Project)

## 📘 Project Overview
This project aims to build a **paper-trading crypto arbitrage bot** capable of detecting price differences between exchanges, simulating trades, and logging profits and losses.  
It is being developed as part of an **IT internship**, focused on Python, APIs, and financial data systems.

---

## 🗓️ Project Timeline

### **Week 0 – Environment & Setup**
**Goal:** Prepare the development environment and connect to exchange testnets.
- Created GitHub repo and local project structure.
- Set up Python virtual environment (`venv`).
- Installed dependencies: `ccxt`, `pandas`, `aiohttp`, `python-dotenv`, etc.
- Created `.env` for secure API key management.
- Generated Binance Testnet API keys and verified connection via `test_binance_auth.py`.

**Deliverable:** Working repo with environment setup, authenticated Binance Testnet access, and sanity check script.

---

### **Week 1 – Exchange Connectivity & API Familiarization**
**Goal:** Establish API connectivity and understand exchange data models.
- Reviewed `ccxt` exchange interfaces and REST endpoints.
- Tested market data retrieval (`fetch_ticker`, `fetch_order_book`, `fetch_trades`).
- Understood rate limits, authentication, and testnet vs live endpoints.
- Logged data samples to JSON and explored API structure.

**Deliverable:** Working Python scripts for market data retrieval and understanding of exchange APIs.

---

### **Week 2 – Python & Data Foundations**
**Goal:** Strengthen Python fundamentals and develop data handling capability for market data.

#### **Daily Breakdown**
- **Day 1:** Python refresh — functions, exceptions, modules, and venv packaging.
- **Day 2:** REST data ingestion — fetch ticker, order book, and trades from Binance.
- **Day 3:** pandas basics — load JSON into DataFrame, compute mid-price & spread.
- **Day 4:** Timestamps & alignment — unify timestamps from two exchanges.
- **Day 5:** Visualization — plot bid/ask/mid data and spreads using `matplotlib`.
- **Day 6:** Documentation — add “Data Format & Timestamping” section.

#### **Deliverables**
- Scripts under `src/` for REST data fetching.
- Jupyter notebooks (`/notebooks`) for data analysis & plotting.
- Updated `README.md` with data format documentation.
- Verified timestamp alignment between Binance & Coinbase test data.

---

## ⚙️ Tech Stack
- **Language:** Python 3.10+
- **Libraries:** `ccxt`, `pandas`, `numpy`, `aiohttp`, `asyncio`, `requests`, `python-dotenv`, `websockets`, `pytest`
- **Data Storage:** JSON & CSV (SQLite planned later)
- **Visualization:** Matplotlib / Jupyter notebooks
- **Version Control:** Git + GitHub
- **Environment:** Virtualenv (`venv`)

---

## 🧾 Data Format & Timestamping
- **Format:** JSON and CSV  
- **Schema Example:**
  ```json
  {
    "symbol": "BTC/USDT",
    "bid": 68000.12,
    "ask": 68010.45,
    "timestamp": 1739126400000,
    "exchange": "binance"
  }
  ```
- **Timestamps:** Converted to UTC (`ISO 8601`) before analysis.
- **Storage Path:** All data saved in `/data/` for reproducibility.

---

## 🚀 How to Run (Development)
```bash
# 1. Clone repo
git clone https://github.com/<your-username>/crypto-arb-bot.git
cd crypto-arb-bot

# 2. Set up environment
python -m venv venv
venv\Scripts\activate  # (Windows CMD)
# or
source venv/bin/activate  # (Mac/Linux)

# 3. Install dependencies
pip install -r requirements.txt

# 4. Set API keys
copy .env.example .env
# fill in BINANCE_API_KEY and BINANCE_API_SECRET

# 5. Run sanity check
python src/test_binance_auth.py
```

---

## 🧭 Next Steps
- Week 3: Real-time data ingestion with WebSockets.  
- Week 4: Simple arbitrage signal detection and backtesting.  
- Week 5: Logging, risk controls, and visualization dashboards.

---

**Maintained by:** Uchiha233 🌹  
**Internship Supervisor:** [Eli]  
**Institution:** Dipper Lab
