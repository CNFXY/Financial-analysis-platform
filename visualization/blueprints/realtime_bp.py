# -*- coding: utf-8 -*-
"""通达信实时行情域路由（REQ-03/05/06 相关接口）。"""
from datetime import datetime
from flask import Blueprint, jsonify, request, render_template

from fund_estimation_system.data_fetcher.tdx_data_reader import TdxDataReader
from fund_estimation_system.data_fetcher.realtime_service import (
    get_alert_engine, get_watchlist_store, get_audit_logger,
)
from fund_estimation_system.visualization.web_server import tdx_realtime

bp = Blueprint("realtime", __name__)
alert_engine = get_alert_engine()
watchlist_store = get_watchlist_store()
audit_logger = get_audit_logger()


def _session_label():
    now = datetime.now()
    if now.weekday() >= 5:
        return "周末休市"
    t = now.hour * 60 + now.minute
    if 9 * 60 + 15 <= t < 9 * 60 + 25:
        return "集合竞价"
    if 9 * 60 + 30 <= t < 11 * 60 + 30 or 13 * 60 <= t < 15 * 60:
        return "盘中交易"
    if 11 * 60 + 30 <= t < 13 * 60:
        return "午间休市"
    return "已收盘(盘后)"


@bp.route("/api/tdx/status")
def api_tdx_status():
    return jsonify(tdx_realtime.status())


@bp.route("/api/tdx/realtime", methods=["POST"])
def api_tdx_realtime():
    data = request.json or {}
    codes = data.get("codes") or data.get("watchlist") or []
    if not codes:
        return jsonify({"error": "请提供 codes", "quotes": []})
    try:
        quotes = tdx_realtime.get_realtime_quotes(codes)
        alerts = []
        for q in quotes:
            alerts.extend(alert_engine.evaluate(q))
        audit_logger.log("realtime_query", {"codes": codes, "count": len(quotes)}, level="INFO")
        return jsonify({
            "server_time": datetime.now().strftime("%H:%M:%S"),
            "trading_session": _session_label(),
            "count": len(quotes), "quotes": quotes, "alerts": alerts,
        })
    except Exception as e:
        return jsonify({"error": f"实时行情失败: {str(e)}", "quotes": []})


@bp.route("/api/tdx/quote", methods=["POST"])
def api_tdx_quote():
    code = (request.json or {}).get("code", "")
    if not code:
        return jsonify({"error": "请提供 code"})
    try:
        q = tdx_realtime.get_single_quote(code)
        if not q:
            return jsonify({"error": f"未获取到行情: {code}"})
        return jsonify({"server_time": datetime.now().strftime("%H:%M:%S"), "quote": q})
    except Exception as e:
        return jsonify({"error": f"报价获取失败: {str(e)}"})


@bp.route("/api/tdx/minute", methods=["POST"])
def api_tdx_minute():
    code = (request.json or {}).get("code", "")
    if not code:
        return jsonify({"error": "请提供 code"})
    try:
        minute = tdx_realtime.get_minute_data(code)
        return jsonify({"code": code, "count": len(minute), "data": minute})
    except Exception as e:
        return jsonify({"error": f"分时获取失败: {str(e)}"})


@bp.route("/api/tdx/kline", methods=["POST"])
def api_tdx_kline():
    data = request.json or {}
    code, ktype, count = data.get("code", ""), data.get("ktype", "day"), int(data.get("count", 120))
    if not code:
        return jsonify({"error": "请提供 code"})
    try:
        kline = tdx_realtime.get_kline(code, ktype=ktype, count=count)
        if not kline:
            return jsonify({"error": f"无K线数据: {code}"})
        return jsonify({"code": code, "ktype": ktype, "count": len(kline), "data": kline})
    except Exception as e:
        return jsonify({"error": f"K线获取失败: {str(e)}"})


@bp.route("/api/tdx/stocks", methods=["GET"])
def api_tdx_stocks():
    reader = TdxDataReader()
    stocks = reader.get_stock_list(market=request.args.get("market", "sz")) or []
    return jsonify({"market": request.args.get("market", "sz"),
                    "stocks": stocks, "count": len(stocks)})


@bp.route("/api/tdx/search", methods=["GET"])
def api_tdx_search():
    q = (request.args.get("q", "") or "").strip()
    if not q:
        return jsonify({"query": q, "results": [], "count": 0})
    try:
        results = tdx_realtime.search(q, limit=20)
        return jsonify({"query": q, "results": results, "count": len(results)})
    except Exception as e:
        return jsonify({"query": q, "error": f"搜索失败: {str(e)}", "results": [], "count": 0})


@bp.route("/api/tdx/data", methods=["POST"])
def api_tdx_data():
    data = request.json or {}
    reader = TdxDataReader()
    if not reader.available:
        return jsonify({"error": "通达信数据目录未找到"})
    df = reader.get_stock_daily(data.get("code", "399001"),
                                start_date=data.get("start_date"), end_date=data.get("end_date"))
    if df is None or df.empty:
        return jsonify({"error": f"未找到数据: {data.get('code', '399001')}"})
    return jsonify({"code": data.get("code", "399001"), "count": len(df),
                    "date_range": [df['date'].min().strftime('%Y-%m-%d'), df['date'].max().strftime('%Y-%m-%d')],
                    "data": df.to_dict('records')})


@bp.route("/api/tdx/info", methods=["GET"])
def api_tdx_info():
    return jsonify(TdxDataReader().get_data_info(request.args.get("code", "399001")))


@bp.route("/realtime")
def realtime_page():
    return render_template("realtime.html")
