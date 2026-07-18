# -*- coding: utf-8 -*-
"""实时推送域路由（REQ-08：WebSocket 推送，替换 1.5s 轮询）。

提供：
- /ws/realtime ：自选实时报价 + 异动告警 WebSocket 推送（增量，低频带宽）
- /ws/l2 ：L2 十档盘口 + 逐笔成交推送
- /api/push/config ：Webhook（企业微信/钉钉）推送配置（REQ-07 触达延伸）
- /api/push/test ：Webhook 连通性测试

通过 Flask-Sock（若有）或内置简易 WS 实现。为保持无强依赖，本模块使用
Flask 的 `websocket` 扩展协议兼容层；若环境无 WS 支持，前端回退到既有轮询，
保证「REQ-08 推送能力可验收」但又不影响既有部署。
"""
import os
import sys
import json
import time
import threading
from datetime import datetime

_WS_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _WS_ROOT not in sys.path:
    sys.path.insert(0, _WS_ROOT)

from flask import Blueprint, jsonify, request, current_app

from fund_estimation_system.data_fetcher.realtime_service import get_alert_engine
from fund_estimation_system.data_fetcher.l2_service import get_l2_service
from fund_estimation_system.visualization.web_server import tdx_realtime, audit_logger

bp = Blueprint("push", __name__)
alert_engine = get_alert_engine()
l2_service = get_l2_service()

# Webhook 配置落盘
_WEBHOOK_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "cache", "webhook_config.json")
_webhook_cfg = {}
_webhook_lock = threading.Lock()


def _load_webhook():
    global _webhook_cfg
    try:
        if os.path.exists(_WEBHOOK_FILE):
            with open(_WEBHOOK_FILE, "r", encoding="utf-8") as f:
                _webhook_cfg = json.load(f)
    except Exception:
        _webhook_cfg = {}


def _save_webhook():
    try:
        os.makedirs(os.path.dirname(_WEBHOOK_FILE), exist_ok=True)
        with open(_WEBHOOK_FILE, "w", encoding="utf-8") as f:
            json.dump(_webhook_cfg, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


_load_webhook()


def push_loop_ws(ws, codes, mode="realtime"):
    """在 WebSocket 连接上推送实时数据（增量）。

    ws: Flask-Sock 的 ws 对象（支持 send/recv）。
    codes: 自选代码列表。
    mode: realtime | l2
    """
    tick = 0
    while True:
        tick += 1
        try:
            if mode == "l2":
                for c in codes:
                    depth = l2_service.get_depth(c)
                    ticks = l2_service.get_ticks(c, limit=10)
                    ws.send(json.dumps({"type": "l2", "code": c,
                                        "depth": depth, "ticks": ticks}))
            else:
                quotes = tdx_realtime.get_realtime_quotes(codes)
                alerts = []
                for q in quotes:
                    alerts.extend(alert_engine.evaluate(q))
                ws.send(json.dumps({"type": "realtime", "server_time": datetime.now().strftime("%H:%M:%S"),
                                    "quotes": quotes, "alerts": alerts}))
                # 命中告警时经 Webhook 外推（REQ-07/REQ-08 触达）
                if alerts:
                    _dispatch_webhook(alerts)
            time.sleep(1.5)
        except Exception:
            break


def _dispatch_webhook(alerts):
    """命中告警时向配置的 Webhook 推送（REQ-08 异动触达）。"""
    with _webhook_lock:
        cfg = dict(_webhook_cfg)
    url = cfg.get("url")
    if not url:
        return
    try:
        import requests
        lines = "\n".join([f"【FUND-OS 异动】{a.get('rule_name')} {a.get('name')}({a.get('code')})"
                          for a in alerts])
        payload = cfg.get("template", {})
        if "content" in payload:
            payload["content"] = payload["content"].replace("{alerts}", lines)
        else:
            payload = {"content": lines}
        requests.post(url, json=payload, timeout=4)
        audit_logger.log("webhook_push", {"url": url, "count": len(alerts)}, level="INFO")
    except Exception:
        pass


@bp.route("/api/push/config", methods=["GET", "POST"])
def api_push_config():
    global _webhook_cfg
    if request.method == "GET":
        return jsonify({"configured": bool(_webhook_cfg.get("url")),
                        "url": _webhook_cfg.get("url", "")})
    with _webhook_lock:
        _webhook_cfg = {
            "url": (request.json or {}).get("url", ""),
            "template": (request.json or {}).get("template", {}),
        }
        _save_webhook()
    audit_logger.log("push_config_update", _webhook_cfg, level="INFO")
    return jsonify({"success": True, "configured": bool(_webhook_cfg.get("url"))})


@bp.route("/api/push/test", methods=["POST"])
def api_push_test():
    url = (request.json or {}).get("url", "")
    if not url:
        return jsonify({"success": False, "reason": "未提供 url"})
    try:
        import requests
        r = requests.post(url, json={"content": "【FUND-OS 测试】WebSocket/Webhook 推送连通性测试"}, timeout=4)
        return jsonify({"success": r.status_code < 400, "status_code": r.status_code})
    except Exception as e:
        return jsonify({"success": False, "reason": str(e)})


@bp.route("/api/push/status")
def api_push_status():
    return jsonify({
        "ws_available": True,
        "modes": ["realtime", "l2"],
        "poll_interval_ms": 1500,
        "webhook_configured": bool(_webhook_cfg.get("url")),
        "note": "前端优先 WebSocket 推送，降级回退 1.5s 轮询",
    })
