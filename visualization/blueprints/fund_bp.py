# -*- coding: utf-8 -*-
"""基金域路由：估值 / 历史 / 对比 / 搜索 / 信息 / K线 / 市场概览。"""
from flask import Blueprint, jsonify, request, render_template

from fund_estimation_system.visualization.data_access import (
    nav_series, date_range,
)
from fund_estimation_system.estimator.fund_nav_estimator import FundNavEstimator
from fund_estimation_system.estimator.portfolio_calculator import PortfolioCalculator
from fund_estimation_system.estimator.risk_analyzer import FundRiskAnalyzer
from fund_estimation_system.report_generator.daily_report import ReportGenerator
from fund_estimation_system.visualization.web_server import (
    estimator, risk_analyzer, report_gen, tdx_realtime,
)

bp = Blueprint("fund", __name__)


@bp.route("/api/fund/estimate", methods=["POST"])
def api_fund_estimate():
    data = request.json or {}
    result = estimator.estimate_fund(
        data.get("code", "510300.SH"),
        fund_type=data.get("type", "cn"),
        method=data.get("method", "lr"),
        stock_changes=data.get("stock_changes"),
        days=int(data.get("days", 20)),
    )
    return jsonify(result)


@bp.route("/api/fund/history", methods=["POST"])
def api_fund_history():
    data = request.json or {}
    fund_code = data.get("code", "510300.SH")
    fund_type = data.get("type", "cn")
    period_days = int(data.get("days", 90))
    dates, navs = nav_series(fund_code, fund_type, period_days)
    if not navs:
        return jsonify({"error": "无数据"})
    return jsonify({"code": fund_code, "data": [{"nav_date": d, "unit_nav": v} for d, v in zip(dates, navs)]})


@bp.route("/api/fund/compare", methods=["POST"])
def api_fund_compare():
    data = request.json or {}
    funds = data.get("funds", [])
    period_days = int(data.get("days", 252))
    if not funds or len(funds) < 2:
        return jsonify({"error": "请至少提供2只基金进行对比"})

    series_list, metrics = [], []
    for f in funds:
        code = (f.get("code") or "").strip()
        if not code:
            continue
        name = f.get("name", code)
        dates, navs = nav_series(code, f.get("type", "cn"), period_days)
        if not navs or len(navs) < 2:
            continue
        res = risk_analyzer.analyze_single_fund(navs, name=name)
        metrics.append({
            "code": code, "name": name,
            "total_return_pct": res.get("total_return_pct", 0),
            "annualized_return_pct": res.get("annualized_return_pct", 0),
            "annualized_volatility_pct": res.get("annualized_volatility_pct", 0),
            "max_drawdown_pct": res.get("max_drawdown", {}).get("max_drawdown_pct", 0),
            "sharpe_ratio": res.get("sharpe_ratio", 0),
            "sortino_ratio": res.get("sortino_ratio", 0),
            "calmar_ratio": res.get("calmar_ratio", 0),
        })
        series_list.append({"code": code, "name": name, "dates": dates, "navs": navs})

    if len(series_list) < 2:
        return jsonify({"error": "有效数据不足，无法对比"})

    min_len = min(len(s["navs"]) for s in series_list)
    labels = series_list[0]["dates"][-min_len:]
    normalized = []
    for s in series_list:
        navs = s["navs"][-min_len:]
        base = navs[0] if navs[0] != 0 else 1
        normalized.append({"code": s["code"], "name": s["name"],
                           "values": [round(v / base * 100, 2) for v in navs]})
    return jsonify({"labels": labels, "series": normalized, "metrics": metrics, "count": len(series_list)})


@bp.route("/api/fund/search", methods=["GET"])
def api_fund_search():
    q = (request.args.get("q", "") or "").strip()
    market = request.args.get("market", "E")
    scope = request.args.get("scope", "all")
    if not q:
        return jsonify({"results": [], "count": 0})
    ql = q.lower()
    results = []
    if scope in ("all", "fund"):
        fl = estimator.ts_client.get_fund_list(market=market)
        if fl is not None and not fl.empty:
            for _, row in fl.iterrows():
                code, name = str(row.get("ts_code", "")), str(row.get("name", ""))
                if ql in code.lower() or ql in name.lower():
                    results.append({"code": code, "name": name, "kind": "基金",
                                    "detail": f"{row.get('fund_type', '')} · {row.get('management', '')}",
                                    "market": row.get("market", market)})
    if scope in ("all", "stock"):
        sl = estimator.ts_client.get_stock_list()
        if sl is not None and not sl.empty:
            for _, row in sl.iterrows():
                code, name = str(row.get("ts_code", "")), str(row.get("name", ""))
                if ql in code.lower() or ql in name.lower():
                    results.append({"code": code, "name": name, "kind": "股票",
                                    "detail": f"{row.get('industry', '')} · {row.get('market', '')}",
                                    "market": "CN"})
    return jsonify({"query": q, "results": results[:20], "count": len(results[:20])})


@bp.route("/api/fund/info", methods=["GET"])
def api_fund_info():
    code = (request.args.get("code", "") or "").strip()
    if not code:
        return jsonify({"error": "请输入基金代码"})
    fl = estimator.ts_client.get_fund_list()
    if fl is not None and not fl.empty:
        m = fl[fl["ts_code"] == code]
        if not m.empty:
            row = m.iloc[0]
            return jsonify({"code": code, "name": row.get("name", ""), "fund_type": row.get("fund_type", ""),
                            "management": row.get("management", ""), "market": row.get("market", "E")})
    return jsonify({"code": code, "name": code, "fund_type": "未知", "management": "未知", "market": "E"})


@bp.route("/api/market/overview", methods=["GET"])
def api_market_overview():
    funds = [
        {"code": "510300.SH", "name": "沪深300ETF", "type": "cn"},
        {"code": "510500.SH", "name": "中证500ETF", "type": "cn"},
        {"code": "159915.SZ", "name": "创业板ETF", "type": "cn"},
        {"code": "SPY", "name": "S&P 500 ETF", "type": "us"},
        {"code": "QQQ", "name": "NASDAQ-100 ETF", "type": "us"},
        {"code": "VTI", "name": "Vanguard Total Stock", "type": "us"},
    ]
    return jsonify(report_gen.generate_market_overview(funds))


@bp.route("/api/fund/kline", methods=["POST"])
def api_fund_kline():
    """K线：优先 TDX 实时 K线，回退 Tushare 股票日线 / 基金净值，海外走 Yahoo。"""
    import pandas as pd
    import numpy as _np
    data = request.json or {}
    fund_code = data.get("code", "510300.SH")
    fund_type = data.get("type", "cn")
    period_days = int(data.get("days", 120))

    if fund_type == "cn":
        try:
            tdx_k = tdx_realtime.get_kline(fund_code, ktype="day", count=period_days)
            if tdx_k:
                kd = [{"date": str(r["date"])[:10], "open": float(r["open"]), "high": float(r["high"]),
                       "low": float(r["low"]), "close": float(r["close"]), "volume": int(r["volume"]),
                       "source": "tdx"} for r in tdx_k]
                return _build_kline_response(fund_code, kd)
        except Exception as e:
            print(f"[WARN] TDX实时K线失败，回退: {e}")

        start, end = date_range(period_days)
        df = None
        try:
            df = estimator.ts_client.get_stock_daily(fund_code, start_date=start, end_date=end)
            if df is not None and not df.empty:
                df = df.sort_values("trade_date").rename(columns={
                    "trade_date": "date", "open": "open", "high": "high",
                    "low": "low", "close": "close", "vol": "volume", "amount": "amount"})
        except Exception as e:
            print(f"[WARN] 股票日线失败，用净值: {e}")
        if df is None or df.empty:
            nav_df = estimator.ts_client.get_fund_nav(fund_code, start_date=start, end_date=end)
            if nav_df is not None and not nav_df.empty:
                nav_df = nav_df.sort_values("nav_date")
                close = nav_df["unit_nav"].astype(float).values
                df = pd.DataFrame({
                    "date": nav_df["nav_date"].values,
                    "open": _np.round(close, 4), "high": _np.round(close, 4),
                    "low": _np.round(close, 4), "close": _np.round(close, 4), "volume": 0,
                })
    else:
        df = estimator.yh_client.get_ticker_data(fund_code, period=f"{period_days}d")
        if df is not None and not df.empty:
            df = df.reset_index().rename(columns={
                "Date": "date", "Open": "open", "High": "high",
                "Low": "low", "Close": "close", "Volume": "volume"})
            df["date"] = df["date"].dt.strftime("%Y-%m-%d")

    if df is None or df.empty or len(df) < 5:
        return jsonify({"error": "数据不足"})
    kd = [{"date": str(r.get("date", "")), "open": float(r.get("open", 0)), "high": float(r.get("high", 0)),
           "low": float(r.get("low", 0)), "close": float(r.get("close", 0)), "volume": int(r.get("volume", 0))}
          for _, row in df.iterrows()]
    return _build_kline_response(fund_code, kd)


def _build_kline_response(fund_code, kline_data):
    if not kline_data or len(kline_data) < 5:
        return jsonify({"error": "数据不足"})
    latest = kline_data[-1]
    prev = kline_data[-2]
    change = latest["close"] - prev["close"]
    change_pct = (change / prev["close"] * 100) if prev["close"] != 0 else 0
    return jsonify({
        "code": fund_code, "name": fund_code,
        "source": "tdx_realtime" if any(k.get("source") == "tdx" for k in kline_data) else "history",
        "count": len(kline_data),
        "latest": {"close": latest["close"], "change": round(change, 4),
                   "change_pct": round(change_pct, 2), "high": latest["high"],
                   "low": latest["low"], "volume": latest["volume"]},
        "data": kline_data,
    })


@bp.route("/fund_estimate")
def fund_estimate_page():
    return render_template("fund_estimate.html")


@bp.route("/compare")
def compare_page():
    return render_template("compare.html")


@bp.route("/reports")
def reports_page():
    return render_template("reports.html")
