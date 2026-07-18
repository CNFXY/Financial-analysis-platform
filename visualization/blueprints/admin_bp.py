# -*- coding: utf-8 -*-
"""后台管理系统蓝图（REQ-17 商务管理后台）。

提供：
- GET  /admin                    后台首页（仪表盘）
- GET  /api/admin/stats          系统统计数据
- GET  /api/admin/tenants        租户列表
- POST /api/admin/tenants        创建租户
- GET  /api/admin/orders         全部订单
- POST /api/admin/orders/:id/refund  订单退款
- GET  /api/admin/system         系统状态（内存/磁盘/进程）
"""
import os
import json
import time
from datetime import datetime, timedelta
from flask import Blueprint, jsonify, request, render_template

# psutil 是可选依赖（系统监控功能）
try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

from fund_estimation_system.data_fetcher.payment_service import get_payment_service

bp = Blueprint("admin", __name__)

CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "..", "cache")
# 实际 cache 路径在项目根目录
_CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "cache")


def _get_cache_path(name):
    p = os.path.join(_CACHE_DIR, name)
    if os.path.exists(p):
        return p
    return os.path.join(CACHE_DIR, name)


def _load_json(name, default=None):
    p = _get_cache_path(name)
    if os.path.exists(p):
        try:
            with open(p, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return default or {}


@bp.route("/admin")
def admin_page():
    """后台管理首页。"""
    return render_template("admin.html")


@bp.route("/api/admin/stats")
def api_admin_stats():
    """系统统计仪表盘。"""
    svc = get_payment_service()
    orders_data = _load_json("billing_orders.json", {"orders": []})
    subs_data = _load_json("subscriptions.json", {"subs": {}})
    
    all_orders = orders_data.get("orders", [])
    
    def _ds(val):
        if isinstance(val, str): return val
        if isinstance(val, (int,float)):
            try: return datetime.fromtimestamp(val).strftime("%Y-%m-%d")
            except: return ""
        return ""
    
    today = datetime.now().strftime("%Y-%m-%d")
    
    # 今日订单
    today_orders = [o for o in all_orders if _ds(o.get("created_at")).startswith(today)]
    # 本月订单
    this_month = datetime.now().strftime("%Y-%m")
    month_orders = [o for o in all_orders if _ds(o.get("created_at")).startswith(this_month)]
    
    # 收入统计
    paid_orders = [o for o in all_orders if o.get("status") == "paid"]
    total_revenue = sum(o.get("amount_cents", 0) for o in paid_orders) / 100
    month_revenue = sum(o.get("amount_cents", 0) for o in paid_orders if _ds(o.get("created_at")).startswith(this_month)) / 100
    
    # 租户统计
    tenants = list(subs_data.get("subs", {}).keys())
    trial_count = sum(1 for s in subs_data.get("subs", {}).values() if s.get("status") == "trial")
    active_count = sum(1 for s in subs_data.get("subs", {}).values() if s.get("status") == "active")
    
    return jsonify({
        "total_tenants": len(tenants),
        "active_tenants": active_count,
        "trial_tenants": trial_count,
        "total_orders": len(all_orders),
        "today_orders": len(today_orders),
        "month_orders": len(month_orders),
        "total_revenue": round(total_revenue, 2),
        "month_revenue": round(month_revenue, 2),
        "plan_distribution": {
            plan: sum(1 for s in subs_data.get("subs", {}).values() if s.get("plan") == plan)
            for plan in ["free", "pro", "enterprise"]
        },
        "recent_orders": sorted(all_orders, key=lambda x: x.get("created_at", ""), reverse=True)[:10],
    })


@bp.route("/api/admin/tenants")
def api_admin_tenants():
    """获取所有租户列表及订阅状态。"""
    svc = get_payment_service()
    subs_data = _load_json("subscriptions.json", {"subs": {}})
    result = []
    for tid, sub in subs_data.get("subs", {}).items():
        plan = svc.get_plan(sub.get("plan", "free"))
        quota = svc.get_quota_status(tid)
        result.append({
            "tenant_id": tid,
            "plan": sub.get("plan"),
            "plan_name": plan.get("name", "") if plan else "",
            "status": sub.get("status"),
            "expires_at": sub.get("expires_at"),
            "created_at": sub.get("created_at"),
            "quota_used_api": quota.get("api_remaining", "?"),
            "quota_watchlist": quota.get("watchlist_used", "?"),
        })
    # 按 tenant_id 排序
    result.sort(key=lambda x: x["tenant_id"])
    return jsonify({"tenants": result})


@bp.route("/api/admin/tenants", methods=["POST"])
def api_admin_create_tenant():
    """创建新租户。"""
    data = request.json or {}
    tenant_id = data.get("tenant_id", "").strip()
    plan = data.get("plan", "free")
    note = data.get("note", "")
    
    if not tenant_id or not re.match(r'^[a-zA-Z0-9_-]+$', tenant_id):
        return jsonify({"success": False, "reason": "tenant_id 只允许字母数字下划线连字符"}), 400
    
    svc = get_payment_service()
    # 检查是否已存在
    existing = svc.get_subscription(tenant_id)
    if existing.get("plan"):
        return jsonify({"success": False, "reason": f"租户 {tenant_id} 已存在"}), 409
    
    result = svc.manual_activate(
        tenant_id=tenant_id,
        plan_code=plan,
        operator="admin",
        note=f"后台创建: {note}"
    )
    return jsonify(result)


@bp.route("/api/admin/orders")
def api_admin_orders():
    """获取全部订单（支持分页和筛选）。"""
    page = int(request.args.get("page", 1))
    limit = min(int(request.args.get("limit", 20)), 100)
    status_filter = request.args.get("status", "")
    plan_filter = request.args.get("plan", "")
    
    orders_data = _load_json("billing_orders.json", {"orders": []})
    all_orders = orders_data.get("orders", [])
    
    # 筛选
    if status_filter:
        all_orders = [o for o in all_orders if o.get("status") == status_filter]
    if plan_filter:
        all_orders = [o for o in all_orders if o.get("plan_code") == plan_filter]
    
    # 按时间倒序
    all_orders.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    
    total = len(all_orders)
    start = (page - 1) * limit
    page_orders = all_orders[start:start + limit]
    
    return jsonify({
        "orders": page_orders,
        "total": total,
        "page": page,
        "limit": limit,
        "pages": (total + limit - 1) // limit,
    })


@bp.route("/api/admin/orders/<order_id>/refund", methods=["POST"])
def api_admin_refund(order_id):
    """订单退款（标记为 refunded）。"""
    orders_data = _load_json("billing_orders.json", {"orders": []})
    for order in orders_data.get("orders", []):
        if order.get("order_id") == order_id:
            if order.get("status") != "paid":
                return jsonify({"success": False, "reason": "只有已支付订单可退款"})
            order["status"] = "refunded"
            order["refunded_at"] = datetime.now().isoformat()
            
            p = _get_cache_path("billing_orders.json")
            with open(p, 'w', encoding='utf-8') as f:
                json.dump(orders_data, f, ensure_ascii=False, indent=2)
            
            return jsonify({"success": True, "message": f"订单 {order_id} 已退款"})
    
    return jsonify({"success": False, "reason": "订单不存在"}, 404)


@bp.route("/api/admin/system")
def api_admin_system():
    """系统资源状态。"""
    if not HAS_PSUTIL:
        return jsonify({"error": "psutil 未安装（pip install psutil）", "cpu_percent": 0, "memory": {}, "disk": {}, "python_processes": 0, "cache_size_mb": 0, "uptime_seconds": 0}), 200
    try:
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        cpu_percent = psutil.cpu_percent(interval=0.5)
        
        # 进程数
        python_procs = len([p for p in psutil.process_iter(['name']) if p.info['name'] == 'python']) if HAS_PSUTIL else 0
        
        # 缓存文件大小
        cache_size = 0
        if os.path.exists(_CACHE_DIR):
            for fn in os.listdir(_CACHE_DIR):
                fp = os.path.join(_CACHE_DIR, fn)
                if os.path.isfile(fp):
                    cache_size += os.path.getsize(fp)
        
        return jsonify({
            "cpu_percent": cpu_percent,
            "memory": {
                "total_gb": round(mem.total / (1024**3), 2),
                "used_gb": round(mem.used / (1024**3), 2),
                "percent": mem.percent,
            },
            "disk": {
                "total_gb": round(disk.total / (1024**3), 2),
                "free_gb": round(disk.free / (1024**3), 2),
                "percent": round(disk.percent, 1),
            },
            "python_processes": python_procs,
            "cache_size_mb": round(cache_size / (1024*1024), 2),
            "uptime_seconds": int(time.time() - psutil.boot_time()) if HAS_PSUTIL else 0,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


import re