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

bp = Blueprint("fund", "__name__")

# 内置常见标的字典：当 Tushare / 本地通达信数据缺失时，为 /api/fund/search 提供兜底。
# 仅静态「代码-名称」映射，不含任何行情/净值数据，不违背「无数据不捏造」原则。
BUILTIN_FUNDS = [
    # 宽基 ETF
    {"code": "510300.SH", "name": "华泰柏瑞沪深300ETF", "kind": "基金", "detail": "宽基指数 · 华泰柏瑞", "market": "E"},
    {"code": "510330.SH", "name": "华夏沪深300ETF", "kind": "基金", "detail": "宽基指数 · 华夏基金", "market": "E"},
    {"code": "159919.SZ", "name": "嘉实沪深300ETF", "kind": "基金", "detail": "宽基指数 · 嘉实基金", "market": "SZ"},
    {"code": "510500.SH", "name": "南方中证500ETF", "kind": "基金", "detail": "宽基指数 · 南方基金", "market": "E"},
    {"code": "161017", "name": "富国中证500指数增强", "kind": "基金", "detail": "宽基指数增强 · 富国", "market": "E"},
    {"code": "159915.SZ", "name": "易方达创业板ETF", "kind": "基金", "detail": "宽基指数 · 易方达", "market": "SZ"},
    {"code": "510050.SH", "name": "华夏上证50ETF", "kind": "基金", "detail": "宽基指数 · 华夏基金", "market": "E"},
    {"code": "110003", "name": "易方达上证50增强", "kind": "基金", "detail": "宽基增强 · 易方达", "market": "E"},
    {"code": "588000.SH", "name": "华夏科创50ETF", "kind": "基金", "detail": "科创板 · 华夏基金", "market": "E"},
    {"code": "159901.SZ", "name": "易方达深证100ETF", "kind": "基金", "detail": "宽基指数 · 易方达", "market": "SZ"},
    # 行业 / 主题
    {"code": "161725", "name": "招商中证白酒指数", "kind": "基金", "detail": "行业指数 · 招商基金", "market": "E"},
    {"code": "012348", "name": "天弘中证食品饮料", "kind": "基金", "detail": "行业指数 · 天弘", "market": "E"},
    {"code": "003096", "name": "中欧医疗健康混合", "kind": "基金", "detail": "医药 · 中欧", "market": "E"},
    {"code": "011609", "name": "国泰中证动漫游戏ETF联接", "kind": "基金", "detail": "行业指数 · 国泰", "market": "E"},
    {"code": "161028", "name": "富国中证新能源汽车", "kind": "基金", "detail": "行业指数 · 富国", "market": "E"},
    {"code": "270042", "name": "广发纳斯达克100指数", "kind": "基金", "detail": "QDII · 广发", "market": "E"},
    {"code": "000834", "name": "大成纳斯达克100", "kind": "基金", "detail": "QDII · 大成", "market": "E"},
    {"code": "161130", "name": "易方达标普500", "kind": "基金", "detail": "QDII · 易方达", "market": "E"},
    # 热门主动 / 混合
    {"code": "110011", "name": "易方达中小盘混合", "kind": "基金", "detail": "混合型 · 易方达", "market": "E"},
    {"code": "005827", "name": "易方达蓝筹精选混合", "kind": "基金", "detail": "混合型 · 易方达", "market": "E"},
    {"code": "163406", "name": "兴全合润混合", "kind": "基金", "detail": "混合型 · 兴证全球", "market": "E"},
    {"code": "260108", "name": "景顺长城新兴成长混合", "kind": "基金", "detail": "混合型 · 景顺", "market": "E"},
    {"code": "000001", "name": "华夏成长混合", "kind": "基金", "detail": "混合型 · 华夏基金", "market": "E"},
    {"code": "320007", "name": "诺安成长混合", "kind": "基金", "detail": "混合型 · 诺安基金", "market": "E"},
    {"code": "519066", "name": "汇添富蓝筹稳健混合", "kind": "基金", "detail": "混合型 · 汇添富", "market": "E"},
    # 债券 / 稳健
    {"code": "050011", "name": "博时信用债券", "kind": "基金", "detail": "债券型 · 博时", "market": "E"},
    {"code": "100018", "name": "富国天利增长债券", "kind": "基金", "detail": "债券型 · 富国", "market": "E"},
]
BUILTIN_STOCKS = [
    {"code": "600519.SH", "name": "贵州茅台", "kind": "股票", "detail": "白酒 · 上交所", "market": "CN"},
    {"code": "000858.SZ", "name": "五粮液", "kind": "股票", "detail": "白酒 · 深交所", "market": "CN"},
    {"code": "601318.SH", "name": "中国平安", "kind": "股票", "detail": "保险 · 上交所", "market": "CN"},
    {"code": "600036.SH", "name": "招商银行", "kind": "股票", "detail": "银行 · 上交所", "market": "CN"},
    {"code": "000001.SZ", "name": "平安银行", "kind": "股票", "detail": "银行 · 深交所", "market": "CN"},
    {"code": "600276.SH", "name": "恒瑞医药", "kind": "股票", "detail": "医药 · 上交所", "market": "CN"},
    {"code": "601012.SH", "name": "隆基绿能", "kind": "股票", "detail": "光伏 · 上交所", "market": "CN"},
    {"code": "600887.SH", "name": "伊利股份", "kind": "股票", "detail": "食品饮料 · 上交所", "market": "CN"},
    {"code": "000333.SZ", "name": "美的集团", "kind": "股票", "detail": "家电 · 深交所", "market": "CN"},
    {"code": "000651.SZ", "name": "格力电器", "kind": "股票", "detail": "家电 · 深交所", "market": "CN"},
    {"code": "300750.SZ", "name": "宁德时代", "kind": "股票", "detail": "新能源 · 创业板", "market": "CN"},
    {"code": "002594.SZ", "name": "比亚迪", "kind": "股票", "detail": "新能源 · 深交所", "market": "CN"},
    {"code": "600900.SH", "name": "长江电力", "kind": "股票", "detail": "电力 · 上交所", "market": "CN"},
    {"code": "601899.SH", "name": "紫金矿业", "kind": "股票", "detail": "有色金属 · 上交所", "market": "CN"},
    {"code": "600030.SH", "name": "中信证券", "kind": "股票", "detail": "券商 · 上交所", "market": "CN"},
    {"code": "000725.SZ", "name": "京东方A", "kind": "股票", "detail": "面板 · 深交所", "market": "CN"},
    {"code": "300059.SZ", "name": "东方财富", "kind": "股票", "detail": "券商 · 创业板", "market": "CN"},
    {"code": "688981.SH", "name": "中芯国际", "kind": "股票", "detail": "半导体 · 科创板", "market": "CN"},
]


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

    def _match(items):
        out = []
        for it in items:
            code = str(it.get("code", ""))
            name = str(it.get("name", ""))
            if ql in code.lower() or ql in name.lower():
                out.append({
                    "code": code,
                    "name": name,
                    "kind": it.get("kind", "基金"),
                    "detail": it.get("detail", ""),
                    "market": it.get("market", market),
                })
        return out

    if scope in ("all", "fund"):
        fl = estimator.ts_client.get_fund_list(market=market)
        if fl is not None and not fl.empty:
            for _, row in fl.iterrows():
                code, name = str(row.get("ts_code", "")), str(row.get("name", ""))
                if ql in code.lower() or ql in name.lower():
                    results.append({"code": code, "name": name, "kind": "基金",
                                    "detail": f"{row.get('fund_type', '')} · {row.get('management', '')}",
                                    "market": row.get("market", market)})
        # 始终以内置字典补充（兜底 + 本地索引补全），去重后追加，提升搜索鲁棒性
        seen = {r["code"] for r in results}
        for it in _match(BUILTIN_FUNDS):
            if it["code"] not in seen:
                results.append(it)
                seen.add(it["code"])
    if scope in ("all", "stock"):
        sl = estimator.ts_client.get_stock_list()
        if sl is not None and not sl.empty:
            for _, row in sl.iterrows():
                code, name = str(row.get("ts_code", "")), str(row.get("name", ""))
                if ql in code.lower() or ql in name.lower():
                    results.append({"code": code, "name": name, "kind": "股票",
                                    "detail": f"{row.get('industry', '')} · {row.get('market', '')}",
                                    "market": "CN"})
        seen = {r["code"] for r in results}
        for it in _match(BUILTIN_STOCKS):
            if it["code"] not in seen:
                results.append(it)
                seen.add(it["code"])
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
    kd = [{"date": str(row.get("date", "")), "open": float(row.get("open", 0)), "high": float(row.get("high", 0)),
           "low": float(row.get("low", 0)), "close": float(row.get("close", 0)), "volume": int(row.get("volume", 0))}
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
