# -*- coding: utf-8 -*-
"""运营支撑域路由：异动告警(REQ-07) / 自选同步(REQ-06) / 审计(REQ-12) / 报告 / 新闻。"""
from flask import Blueprint, jsonify, request, render_template

from fund_estimation_system.data_fetcher.realtime_service import (
    get_alert_engine, get_watchlist_store, get_audit_logger,
    get_risk_engine, get_paper_engine,
)
from fund_estimation_system.data_fetcher.tenant_service import (
    get_tenant_service, ROLE_NAMES,
)
from fund_estimation_system.report_generator.daily_report import ReportGenerator
from fund_estimation_system.data_fetcher.news_fetcher import NewsFetcher
from fund_estimation_system.visualization.web_server import report_gen

bp = Blueprint("ops", __name__)
alert_engine = get_alert_engine()
watchlist_store = get_watchlist_store()
audit_logger = get_audit_logger()
risk_engine = get_risk_engine()
paper_engine = get_paper_engine()
tenant_svc = get_tenant_service()
news_fetcher = NewsFetcher()


# ---------- 异动告警 (REQ-07) ----------
@bp.route("/api/alert/rules", methods=["GET", "POST", "DELETE"])
def api_alert_rules():
    audit_logger.log("alert_rule_op", {"method": request.method}, level="INFO")
    if request.method == "GET":
        return jsonify({"rules": alert_engine.list_rules()})
    if request.method == "POST":
        rid = alert_engine.add_rule(request.json or {})
        return jsonify({"success": True, "id": rid, "rule": alert_engine.list_rules()})
    rid = request.args.get("id", "")
    return jsonify({"success": alert_engine.remove_rule(rid)})


@bp.route("/api/alert/check", methods=["POST"])
def api_alert_check():
    quotes = (request.json or {}).get("quotes", [])
    alerts = []
    for q in quotes:
        alerts.extend(alert_engine.evaluate(q))
    return jsonify({"alerts": alerts})


# ---------- 自选云端同步 (REQ-06) ----------
@bp.route("/api/watchlist", methods=["GET", "POST", "DELETE", "PUT"])
def api_watchlist():
    if request.method == "GET":
        return jsonify(watchlist_store.get_all())
    if request.method == "POST":
        data = request.json or {}
        code = (data.get("code") or "").strip()
        group = data.get("group", "default")
        if not code:
            return jsonify({"error": "请提供 code"})
        watchlist_store.add(code, group)
        audit_logger.log("watchlist_add", {"code": code, "group": group}, level="INFO")
        return jsonify({"success": True, "groups": watchlist_store.get_all()})
    if request.method == "DELETE":
        code = request.args.get("code", "").strip()
        group = request.args.get("group", "default")
        if not code:
            return jsonify({"error": "请提供 code"})
        watchlist_store.remove(code, group)
        audit_logger.log("watchlist_remove", {"code": code, "group": group}, level="INFO")
        return jsonify({"success": True, "groups": watchlist_store.get_all()})
    data = request.json or {}
    watchlist_store.set_group(data.get("group", "default"), data.get("codes", []))
    return jsonify({"success": True, "groups": watchlist_store.get_all()})


@bp.route("/api/watchlist/import", methods=["POST"])
def api_watchlist_import():
    text = (request.json or {}).get("text", "")
    added = watchlist_store.import_csv(text)
    audit_logger.log("watchlist_import", {"count": len(added)}, level="INFO")
    return jsonify({"success": True, "added": added, "groups": watchlist_store.get_all()})


# ---------- 操作审计 (REQ-12 / P0-4 落库) ----------
@bp.route("/api/audit/recent", methods=["GET"])
def api_audit_recent():
    return jsonify({"logs": audit_logger.recent(int(request.args.get("limit", 200)))})


@bp.route("/api/audit/query", methods=["GET"])
def api_audit_query():
    """结构化检索审计事件（P0-4：可检索）。"""
    return jsonify({"records": audit_logger.query(
        action=request.args.get("action"),
        operator=request.args.get("operator"),
        level=request.args.get("level"),
        limit=int(request.args.get("limit", 500)))})


@bp.route("/api/audit/export", methods=["GET"])
def api_audit_export():
    """导出审计为 CSV（P0-4：可导出）。"""
    from flask import Response
    csv_text = audit_logger.export_csv()
    return Response(csv_text, mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=audit.csv"})


# ---------- 风控引擎 (P0-4) ----------
@bp.route("/api/risk/config", methods=["GET", "POST"])
def api_risk_config():
    if request.method == "GET":
        return jsonify(risk_engine.get_config())
    cfg = risk_engine.update_config(request.json or {})
    audit_logger.log("risk_config_update", request.json or {}, level="WARN")
    return jsonify({"success": True, "config": cfg})


# ---------- 模拟盘交易 (P0-3) ----------
@bp.route("/api/trade/account", methods=["GET", "POST"])
def api_trade_account():
    """账户快照。POST 可带 {price_map:{code:price}} 刷新持仓市值。"""
    price_map = (request.json or {}).get("price_map") if request.method == "POST" else None
    return jsonify(paper_engine.account(price_map))


@bp.route("/api/trade/order", methods=["POST"])
def api_trade_order():
    """下单（市价即时撮合，下单前强制风控校验）。"""
    from fund_estimation_system.availability.ha_service import get_ha_metrics
    d = request.json or {}
    res = paper_engine.place_order(
        code=(d.get("code") or "").strip(), side=d.get("side"),
        price=d.get("price"), qty=d.get("qty"), name=d.get("name", ""))
    # REQ-10：记录下单成功率指标
    get_ha_metrics().record_order(bool(res.get("success")))
    return jsonify(res)


@bp.route("/api/trade/cancel", methods=["POST"])
def api_trade_cancel():
    return jsonify(paper_engine.cancel_order((request.json or {}).get("order_id", "")))


@bp.route("/api/trade/stopcheck", methods=["POST"])
def api_trade_stopcheck():
    """止损止盈监测。传入 {price_map} 返回命中列表（P0-4）。"""
    price_map = (request.json or {}).get("price_map", {})
    return jsonify({"hits": paper_engine.check_stop(price_map)})


# ---------- 报告 ----------
@bp.route("/api/report/fund_detail", methods=["POST"])
def api_fund_detail_report():
    data = request.json or {}
    return jsonify(report_gen.generate_fund_detail_report(
        data.get("code", "510300.SH"), data.get("type", "cn")))


@bp.route("/api/report/generate", methods=["POST"])
def api_generate_report():
    data = request.json or {}
    rtype = data.get("report_type", "overview")
    if rtype == "overview":
        rd = report_gen.generate_market_overview()
    elif rtype == "portfolio":
        rd = report_gen.generate_portfolio_report(data.get("holdings", []))
    else:
        return jsonify({"error": "未知报告类型"})
    return jsonify({"success": True, "path": report_gen.save_report(rd, rtype)})


# ---------- 新闻 ----------
@bp.route("/api/news/global", methods=["GET"])
def api_news_global():
    try:
        return jsonify(news_fetcher.fetch_news(
            category=request.args.get("category", "all"),
            region=request.args.get("region", "all"),
            limit=int(request.args.get("limit", 40))))
    except Exception as e:
        return jsonify({"error": f"新闻获取失败: {str(e)}"})


# ---------- 多租户与角色权限 (REQ-06) ----------
@bp.route("/api/tenant/seats", methods=["GET"])
def api_tenant_seats():
    """列出某租户下的席位与角色（权限分级核验）。"""
    tid = request.args.get("tenant", "demo")
    return jsonify({
        "tenant": tid,
        "seats": tenant_svc.list_seats(tid),
        "role_names": ROLE_NAMES,
    })


@bp.route("/api/tenant/seat/permission", methods=["GET"])
def api_tenant_perm():
    """校验席位权限（REQ-06 隔离生效核验）。"""
    tid = request.args.get("tenant", "demo")
    seat = request.args.get("seat", "")
    perm = request.args.get("perm", "")
    if not seat:
        return jsonify({"error": "请提供 seat"})
    return jsonify({
        "tenant": tid,
        "seat": seat,
        "permission": perm,
        "granted": tenant_svc.has_permission(seat, perm, tid),
        "all_permissions": tenant_svc.permissions_of(seat, tid),
    })


@bp.route("/api/tenant/watchlist", methods=["GET", "POST"])
def api_tenant_watchlist():
    """租户隔离的自选（多人共享、按租户隔离）。"""
    tid = request.args.get("tenant", "demo")
    group = request.args.get("group", "default")
    if request.method == "GET":
        return jsonify({"tenant": tid, "group": group,
                        "codes": tenant_svc.get_watchlist(tid, group)})
    codes = (request.json or {}).get("codes", [])
    return jsonify({"tenant": tid, "group": group,
                    "codes": tenant_svc.set_watchlist(codes, tid, group)})


# ---------- 页面 ----------
@bp.route("/l2")
def l2_page():
    return render_template("l2.html")


@bp.route("/")
def index():
    return render_template("index.html")


@bp.route("/news")
def news_page():
    return render_template("news.html")


@bp.route("/principles")
def principles_page():
    return render_template("principles.html")
