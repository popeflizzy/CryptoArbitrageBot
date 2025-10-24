# WebSocket API Summary — Day 1  
### Exchanges: Binance & Coinbase  
### Pair: BTC/USDT  
### Channels: Trades · Orderbook · Ticker  

---

## 🔹 Exchange 1: Binance (Spot)

**Docs:**  
https://binance-docs.github.io/apidocs/spot/en/#websocket-market-streams  

**Base Endpoint:**  
`wss://stream.binance.com:9443/ws`

---

### **1. Channels**

| Channel | Description | Subscribe Example |
|----------|--------------|-------------------|
| **Trade** | Real-time individual trades | `{"method":"SUBSCRIBE","params":["btcusdt@trade"],"id":1}` |
| **Orderbook (Depth)** | Incremental orderbook updates | `{"method":"SUBSCRIBE","params":["btcusdt@depth"],"id":2}` |
| **BookTicker** | Best bid/ask updates | `{"method":"SUBSCRIBE","params":["btcusdt@bookTicker"],"id":3}` |

---

### **2. Example Payloads**

**Trade Event Example:**
```json
{
  "e": "trade",
  "E": 1712345678901,
  "s": "BTCUSDT",
  "t": 12345678,
  "p": "68750.10",
  "q": "0.002",
  "b": 100,
  "a": 200,
  "T": 1712345678899,
  "m": true
}
```
- `E` → event time (ms)  
- `p` → price, `q` → quantity  
- `m` → `true` if buyer is market maker  

**Depth Update Example:**
```json
{
  "e": "depthUpdate",
  "E": 1712345678901,
  "s": "BTCUSDT",
  "U": 157,
  "u": 160,
  "b": [["68750.10", "0.002"]],
  "a": [["68751.00", "0.001"]]
}
```
- `b` = bid updates `[price, qty]`  
- `a` = ask updates `[price, qty]`

**BookTicker Example:**
```json
{
  "u": 400900217,
  "s": "BTCUSDT",
  "b": "68750.00",
  "B": "1.234",
  "a": "68750.10",
  "A": "2.345"
}
```
- `b/B` → best bid price/qty  
- `a/A` → best ask price/qty  

---

### **3. Connection Details**
- **Ping/Pong:** Automatically handled by Binance server.  
- **Timestamps:** Milliseconds since epoch (UTC).  
- **Reconnect:** Simply reconnect to the same stream; use backoff if frequent disconnects.  
- **Rate Limits:** 5 requests per second per connection.  
- **Notes:** Multiple streams can be combined:  
  `wss://stream.binance.com:9443/stream?streams=btcusdt@trade/btcusdt@bookTicker`

---

## 🔹 Exchange 2: Coinbase Exchange

**Docs:**  
https://docs.cloud.coinbase.com/exchange/docs/websocket-overview  

**Base Endpoint:**  
`wss://ws-feed.exchange.coinbase.com`

---

### **1. Channels**

| Channel | Description | Subscribe Example |
|----------|--------------|-------------------|
| **Matches (Trades)** | Executed trades feed | `{"type":"subscribe","channels":[{"name":"matches","product_ids":["BTC-USD"]}]}` |
| **Level2 (Orderbook)** | Incremental orderbook updates | `{"type":"subscribe","channels":[{"name":"level2","product_ids":["BTC-USD"]}]}` |
| **Ticker** | Best bid/ask summary | `{"type":"subscribe","channels":[{"name":"ticker","product_ids":["BTC-USD"]}]}` |

---

### **2. Example Payloads**

**Trade (Match) Event Example:**
```json
{
  "type": "match",
  "trade_id": 12345678,
  "maker_order_id": "abc",
  "taker_order_id": "xyz",
  "side": "buy",
  "price": "68750.10",
  "size": "0.002",
  "product_id": "BTC-USD",
  "time": "2025-10-24T08:12:34.567Z"
}
```

**Orderbook (Level2) Update Example:**
```json
{
  "type": "l2update",
  "product_id": "BTC-USD",
  "time": "2025-10-24T08:12:35.789Z",
  "changes": [["buy", "68750.00", "0.001"]]
}
```

**Ticker Example:**
```json
{
  "type": "ticker",
  "sequence": 12345678,
  "product_id": "BTC-USD",
  "price": "68750.10",
  "best_bid": "68750.00",
  "best_ask": "68750.20",
  "time": "2025-10-24T08:12:36.000Z"
}
```

---

### **3. Connection Details**
- **Ping/Pong:** Coinbase expects a `pong` reply if the server sends `ping`.  
- **Timestamps:** ISO 8601 UTC (e.g., `"2025-10-24T08:12:34.567Z"`).  
- **Reconnect:** Wait at least 5 s before reconnecting after disconnect.  
- **Rate Limits:** ~1 message/sec for public feed (per connection).  
- **Notes:** You can subscribe to multiple product_ids in one request.

---

## 🔸 Comparison Table

| Feature | Binance | Coinbase |
|----------|----------|-----------|
| **Base URL** | `wss://stream.binance.com:9443/ws` | `wss://ws-feed.exchange.coinbase.com` |
| **Pair Format** | BTCUSDT | BTC-USD |
| **Timestamp Format** | Epoch ms | ISO 8601 UTC |
| **Ping Handling** | Auto (server side) | Manual (respond `pong`) |
| **Rate Limit** | 5 req/sec | ~1 msg/sec |
| **Reconnect Rule** | Simple reconnect | Wait ≥ 5 s |
| **Trade Channel** | `@trade` | `matches` |
| **Orderbook Channel** | `@depth` | `level2` |
| **Ticker Channel** | `@bookTicker` | `ticker` |

---

## ✅ Summary Notes

- Both exchanges provide live **trade**, **orderbook**, and **ticker** feeds for BTC/USDT (BTC-USD on Coinbase).  
- Binance timestamps are numeric (milliseconds); Coinbase uses readable ISO UTC strings.  
- Coinbase requires periodic **pong** responses; Binance does not.  
- These details will guide the async WebSocket client implementations starting **Day 2**.

---

**End of Day 1 Deliverable — `websocket_doc_summary.md`**
