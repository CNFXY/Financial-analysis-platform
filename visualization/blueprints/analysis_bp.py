# -*- coding: utf-8 -*-
"""组合 / 风险 / 技术指标 / 估值锚定 / 回测 域路由。"""
from flask import Blueprint, jsonify, request, render_template

from fund_estimation_system.visualization.data_access import nav_series, date_range
from fund_estimation_system.estimator.portfolio_calculator import PortfolioCalculator
from fund_estimation_system.estimator.risk_analyzer import FundRiskAnalyzer
from fund_estimation_system.estimator.tech_indicators import TechnicalIndicators
from fund_estimation_system.estimator.valuation_backtest import ValuationBacktest
from fund_estimation_system.visualization.web_server import (
    estimator, portfolio_calc, risk_analyzer, valuation_bt,
)
from fund_estimation_system.core.billing_guard import require_subscription

bp = Blueprint("analysis", __name__)


@bp.route("/api/portfolio/calculate", methods=["POST"])
def api_portfolio_calculate():
    holdings = request.json.get("holdings", []) if request.json else []
    if not holdings:
        return jsonify({"error": "持仓数据为空"})
    return jsonify(portfolio_calc.calculate_portfolio(holdings))


@bp.route("/api/portfolio/history", methods=["POST"])
def api_portfolio_history():
    data = request.json or {}
    return jsonify(portfolio_calc.calculate_historical_returns(
        data.get("code", "510300.SH"), data.get("type", "cn_fund"), int(data.get("days", 252))))


@bp.route("/api/portfolio/backtest", methods=["POST"])
@require_subscription(feature="backtest")
def api_portfolio_backtest():
    data = request.json or {}
    holdings = data.get("holdings", [])
    if not holdings:
        return jsonify({"error": "持仓数据为空"})
    try:
        return jsonify(portfolio_calc.simulate_portfolio_history(
            holdings, period_days=int(data.get("days", 252))))
    except Exception as e:
        return jsonify({"error": f"组合回测失败: {str(e)}"})


@bp.route("/api/risk/analyze", methods=["POST"])
def api_risk_analyze():
    data = request.json or {}
    code, ftype, period = data.get("code", "510300.SH"), data.get("type", "cn"), int(data.get("days", 252))
    dates, navs = nav_series(code, ftype, period)
    if not navs or len(navs) < 30:
        return jsonify({"error": "数据不足"})
    bench = None
    if data.get("benchmark_code"):
        bd, bn = nav_series(data["benchmark_code"], ftype, period)
        bench = bn
    try:
        return jsonify(risk_analyzer.analyze_single_fund(navs, name=code, benchmark_navs=bench))
    except Exception as e:
        return jsonify({"error": f"风险分析失败: {str(e)}"})


@bp.route("/api/risk/portfolio", methods=["POST"])
@require_subscription(feature="risk_full")
def api_risk_portfolio():
    data = request.json or {}
    funds = data.get("funds", [])
    if not funds:
        return jsonify({"error": "请提供基金列表"})
    nav_dict, weights = {}, {}
    for f in funds:
        code, ftype = f["code"], f.get("type", "cn")
        weights[code] = f.get("weight", 1.0 / len(funds))
        d, n = nav_series(code, ftype, int(data.get("days", 252)))
        if n:
            nav_dict[code] = n
    if len(nav_dict) < 2:
        return jsonify({"error": "数据不足，无法计算相关性"})
    try:
        return jsonify(risk_analyzer.analyze_portfolio(nav_dict, portfolio_weights=weights))
    except Exception as e:
        return jsonify({"error": f"组合风险分析失败: {str(e)}"})


@bp.route("/api/tech/indicators", methods=["POST"])
def api_tech_indicators():
    from flask import jsonify as _j
    data = request.json or {}
    code, ftype, period = data.get("code", "510300.SH"), data.get("type", "cn"), int(data.get("days", 120))
    dates, navs = nav_series(code, ftype, period)
    if not navs or len(navs) < 30:
        return _j({"error": "数据不足，需要至少30个交易日"})
    import pandas as pd
    df = pd.DataFrame({"date": dates, "close": navs,
                       "open": navs, "high": navs, "low": navs, "volume": 0})
    try:
        res = TechnicalIndicators.compute_all(df)
        df_json = res["dataframe"].fillna("N/A").to_dict("records")[-30:]
        return _j({"code": code, "indicators": df_json, "signals": res["signals"], "metadata": res["metadata"]})
    except Exception as e:
        return _j({"error": f"技术指标计算失败: {str(e)}"})


@bp.route("/api/valuation/anchor", methods=["POST"])
@require_subscription(feature="valuation")
def api_valuation_anchor():
    data = request.json or {}
    try:
        return jsonify(valuation_bt.valuation_anchor(
            data.get("code", "510300.SH"), asset_type=data.get("type", "cn"), period_days=int(data.get("days", 504))))
    except Exception as e:
        return jsonify({"error": f"估值锚定失败: {str(e)}"})


@bp.route("/api/backtest/run", methods=["POST"])
@require_subscription(feature="backtest")
def api_backtest_run():
    data = request.json or {}
    try:
        # REQ-05：guardrails=1 时启用防过拟合护栏（样本外/参数敏感性/过拟合评分）
        if str(data.get("guardrails", "")) in ("1", "true", "True"):
            return jsonify(valuation_bt.backtest_with_guardrails(
                data.get("code", "510300.SH"), asset_type=data.get("type", "cn"),
                period_days=int(data.get("days", 504)),
                strategy=data.get("strategy", "ma_cross"),
                oos_ratio=float(data.get("oos_ratio", 0.3))))
        return jsonify(valuation_bt.backtest(
            data.get("code", "510300.SH"), asset_type=data.get("type", "cn"),
            period_days=int(data.get("days", 504)), strategy=data.get("strategy", "ma_cross")))
    except Exception as e:
        return jsonify({"error": f"策略回测失败: {str(e)}"})


@bp.route("/api/backtest/export", methods=["POST"])
@require_subscription(feature="export")
def api_backtest_export():
    """回测报告导出（REQ-05 导出守卫：未通过护栏禁止导出）。"""
    from flask import Response
    data = request.json or {}
    try:
        result = valuation_bt.backtest_with_guardrails(
            data.get("code", "510300.SH"), asset_type=data.get("type", "cn"),
            period_days=int(data.get("days", 504)),
            strategy=data.get("strategy", "ma_cross"),
            oos_ratio=float(data.get("oos_ratio", 0.3)))
        ok, msg = valuation_bt.can_export_report(result)
        if not ok:
            return jsonify({"error": msg}), 403
        # 通过护栏，返回结构化 JSON 报告（含样本内/外显著标注）
        return Response(json.dumps(result, ensure_ascii=False, indent=2),
                        mimetype="application/json",
                        headers={"Content-Disposition": "attachment; filename=backtest_report.json"})
    except Exception as e:
        return jsonify({"error": f"导出失败: {str(e)}"})


@bp.route("/portfolio")
def portfolio_page():
    return render_template("portfolio.html")


@bp.route("/tech_analysis")
def tech_analysis_page():
    return render_template("tech_analysis.html")


@bp.route("/risk_analysis")
def risk_analysis_page():
    return render_template("risk_analysis.html")


@bp.route("/valuation")
def valuation_page():
    return render_template("valuation.html")


@bp.route("/backtest")
def backtest_page():
    return render_template("backtest.html")
