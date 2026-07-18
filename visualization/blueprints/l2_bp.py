# -*- coding: utf-8 -*-
"""L2 行情深度域路由（REQ-04）。"""
from flask import Blueprint, jsonify, request

from fund_estimation_system.data_fetcher.l2_service import get_l2_service
from fund_estimation_system.visualization.web_server import tdx_realtime, audit_logger

bp = Blueprint("l2", __name__)
l2_service = get_l2_service()


@bp.route("/api/l2/depth", methods=["GET", "POST"])
def api_l2_depth():
    code = (request.args.get("code") or (request.json or {}).get("code", "")).strip()
    if not code:
        return jsonify({"error": "请提供 code"})
    try:
        depth = l2_service.get_depth(code)
        return jsonify(depth)
    except Exception as e:
        return jsonify({"error": f"L2盘口获取失败: {str(e)}"})


@bp.route("/api/l2/ticks", methods=["GET", "POST"])
def api_l2_ticks():
    data = request.args if request.method == "GET" else (request.json or {})
    code = (data.get("code") or "").strip()
    last_id = int(data.get("last_id", 0) or 0)
    limit = int(data.get("limit", 50) or 50)
    if not code:
        return jsonify({"error": "请提供 code", "ticks": []})
    try:
        ticks = l2_service.get_ticks(code, last_id=last_id, limit=limit)
        return jsonify({"code": code, "last_id": ticks[-1]["id"] if ticks else last_id,
                        "count": len(ticks), "ticks": ticks})
    except Exception as e:
        return jsonify({"error": f"逐笔成交获取失败: {str(e)}", "ticks": []})


@bp.route("/api/l2/sweep_accuracy", methods=["GET"])
def api_l2_sweep():
    code = (request.args.get("code") or "").strip()
    if not code:
        return jsonify({"error": "请提供 code"})
    return jsonify(l2_service.sweep_accuracy(code))


@bp.route("/api/l2/status")
def api_l2_status():
    """L2 能力状态（前端展示数据源是否提供真实 L2）。"""
    return jsonify({
        "l2_supported": True,
        "sim_fallback": True,
        "note": "十档盘口/逐笔成交：授权源实现 /l2 契约时走真实数据，否则仿真可用",
    })
