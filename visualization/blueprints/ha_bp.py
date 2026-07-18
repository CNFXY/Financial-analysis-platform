# -*- coding: utf-8 -*-
"""高可用与可观测域路由（REQ-10）。"""
from flask import Blueprint, Response, jsonify

from fund_estimation_system.availability.ha_service import get_ha_metrics

bp = Blueprint("ha", __name__)


def _tdx_realtime():
    """惰性获取实时行情单例，避免模块加载期触发 web_server 完整初始化（循环导入）。"""
    from fund_estimation_system.visualization.web_server import tdx_realtime
    return tdx_realtime


@bp.route("/healthz")
def healthz():
    """增强健康检查（REQ-10）：含数据源降级状态与 SLA 关键指标。"""
    s = _tdx_realtime().status()
    metrics = get_ha_metrics().snapshot()
    healthy = bool(s.get("connected")) and not s.get("stale")
    return jsonify({
        "status": "ok" if healthy else "degraded",
        "active_source": s.get("active_source"),
        "degraded": s.get("degraded"),
        "latency_level": s.get("latency_level"),
        "uptime_sec": metrics["uptime_sec"],
        "quote_success_rate": metrics["quote_success_rate"],
        "order_success_rate": metrics["order_success_rate"],
    }), 200 if healthy else 200  # 进程存活即 200，降级信息在 body


@bp.route("/metrics")
def metrics():
    """Prometheus 格式指标（REQ-10 监控抓取端点）。"""
    return Response(get_ha_metrics().prometheus(), mimetype="text/plain")


@bp.route("/api/ha/status")
def api_ha_status():
    """面向前端/运维的 HA 状态面板数据。"""
    s = _tdx_realtime().status()
    return jsonify({
        "active_source": s.get("active_source"),
        "degraded": s.get("degraded"),
        "latency_level": s.get("latency_level"),
        "latency_ms": s.get("latency_ms"),
        "metrics": get_ha_metrics().snapshot(),
        "multi_instance": False,  # 单实例；多活由外部 LB + 多副本实现
        "note": "单实例自愈+降级已具备；多活需 nginx/gunicorn 多副本 + 本 /metrics 抓取",
    })
