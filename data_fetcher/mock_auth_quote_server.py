# -*- coding: utf-8 -*-
"""模拟授权行情源（REQ-01 验收用）。

用途：
- 演示/验收阶段，作为「授权行情主源」运行，证明 QuoteProviderHub 的
  「主源优先 + 断连自动降级」链路**真实可跑**（非占位）。
- 生产环境用真实授权源 URL 替换：设置环境变量
  QUOTE_ENDPOINT=http://real-auth-provider  QUOTE_TOKEN=xxx 即可，
  无需改动任何上层代码。

协议（与 AuthQuoteProvider 约定一致）：
  GET /status      -> {"ok": true}
  GET /quotes?codes=600519,000001 -> {"data":[{code,name,price,last_close,...}]}
  GET /minute?code=600519        -> {"data":[{price,vol,time}]}
  GET /kline?code=&ktype=&count= -> {"data":[{date,open,close,high,low,volume,amount}]}
  GET /search?q=&limit=          -> {"data":[{code,name,market,kind}]}
鉴权：Authorization: Bearer <token>
"""
import os
import sys
import json
import random
from datetime import datetime, timedelta

# 确保工作区根目录在导入路径中（脚本独立运行时）
_WS_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _WS_ROOT not in sys.path:
    sys.path.insert(0, _WS_ROOT)

from flask import Flask, request, jsonify


app = Flask(__name__)
_TOKEN = os.environ.get("MOCK_QUOTE_TOKEN", "demo-auth-token")

# 演示用样本行情（模拟授权源下发的真实结构数据，避免依赖外部行情连接）
_SAMPLE = {
    "600519": {"name": "贵州茅台", "market": "上海", "price": 1685.0, "last_close": 1700.0,
               "open": 1698.0, "high": 1710.0, "low": 1680.0, "volume": 3200000, "amount": 5.4e9,
               "bid1": 1684.5, "ask1": 1685.5, "bid_vol1": 1200, "ask_vol1": 980},
    "000001": {"name": "平安银行", "market": "深圳", "price": 11.85, "last_close": 11.92,
               "open": 11.90, "high": 12.05, "low": 11.80, "volume": 56000000, "amount": 6.7e8,
               "bid1": 11.84, "ask1": 11.85, "bid_vol1": 45000, "ask_vol1": 38000},
    "300750": {"name": "宁德时代", "market": "深圳", "price": 182.3, "last_close": 180.1,
               "open": 181.0, "high": 184.2, "low": 179.5, "volume": 21000000, "amount": 3.8e9,
               "bid1": 182.2, "ask1": 182.3, "bid_vol1": 8200, "ask_vol1": 7600},
    "510300": {"name": "沪深300ETF", "market": "上海", "price": 3.92, "last_close": 3.95,
               "open": 3.94, "high": 3.97, "low": 3.90, "volume": 120000000, "amount": 4.7e8,
               "bid1": 3.91, "ask1": 3.92, "bid_vol1": 980000, "ask_vol1": 870000},
}


def _jitter(v, pct=0.002):
    return round(v * (1 + random.uniform(-pct, pct)), 3)


@app.route("/status")
def status():
    return jsonify({"ok": True, "source": "mock_auth_quote_provider"})


@app.route("/quotes")
def quotes():
    token = request.headers.get("Authorization", "")
    if token != f"Bearer {_TOKEN}":
        return jsonify({"error": "unauthorized"}), 401
    codes = (request.args.get("codes") or "").split(",")
    out = []
    for c in codes:
        c = c.strip()
        if not c:
            continue
        s = _SAMPLE.get(c)
        if not s:
            continue
        out.append({
            "code": c, "name": s["name"], "market": s["market"],
            "price": _jitter(s["price"]), "last_close": s["last_close"],
            "open": s["open"], "high": s["high"], "low": s["low"],
            "volume": s["volume"], "amount": s["amount"],
            "bid1": s["bid1"], "ask1": s["ask1"],
            "bid_vol1": s["bid_vol1"], "ask_vol1": s["ask_vol1"],
            "servertime": datetime.now().strftime("%H:%M:%S"),
        })
    return jsonify({"data": out})


@app.route("/minute")
def minute():
    token = request.headers.get("Authorization", "")
    if token != f"Bearer {_TOKEN}":
        return jsonify({"error": "unauthorized"}), 401
    code = request.args.get("code", "")
    s = _SAMPLE.get(code)
    if not s:
        return jsonify({"data": []})
    base = s["price"]
    data = []
    now = datetime.now().replace(second=0, microsecond=0)
    for i in range(60):
        t = (now - timedelta(minutes=59 - i))
        data.append({"price": _jitter(base, 0.003), "vol": random.randint(1000, 8000),
                     "time": t.strftime("%H:%M")})
    return jsonify({"data": data})


@app.route("/kline")
def kline():
    token = request.headers.get("Authorization", "")
    if token != f"Bearer {_TOKEN}":
        return jsonify({"error": "unauthorized"}), 401
    code = request.args.get("code", "")
    count = int(request.args.get("count", 120))
    s = _SAMPLE.get(code)
    if not s:
        return jsonify({"data": []})
    base = s["last_close"]
    data = []
    today = datetime.now().date()
    for i in range(count):
        d = today - timedelta(days=count - 1 - i)
        close = _jitter(base * (1 + 0.0005 * (i - count / 2)), 0.01)
        data.append({"date": d.strftime("%Y-%m-%d"), "open": _jitter(close),
                     "close": close, "high": _jitter(close, 0.01),
                     "low": _jitter(close, 0.01), "volume": random.randint(1e6, 9e7),
                     "amount": random.uniform(1e8, 9e9)})
    return jsonify({"data": data})


@app.route("/search")
def search():
    token = request.headers.get("Authorization", "")
    if token != f"Bearer {_TOKEN}":
        return jsonify({"error": "unauthorized"}), 401
    q = (request.args.get("q") or "").strip()
    limit = int(request.args.get("limit", 20))
    data = []
    for c, s in _SAMPLE.items():
        if q in c or q in s["name"]:
            data.append({"code": c, "name": s["name"], "market": s["market"], "kind": "股票/ETF"})
        if len(data) >= limit:
            break
    return jsonify({"data": data})


if __name__ == "__main__":
    port = int(os.environ.get("MOCK_QUOTE_PORT", 5011))
    print(f"[MockAuthQuote] 模拟授权行情源启动: http://0.0.0.0:{port}  token={_TOKEN}")
    app.run(host="0.0.0.0", port=port, debug=False)
