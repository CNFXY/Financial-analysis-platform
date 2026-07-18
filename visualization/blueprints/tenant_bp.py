# -*- coding: utf-8 -*-
"""多租户 / 角色权限域路由（REQ-06）。

提供：
- 席位（Seat）管理：列表 / 新增 / 移除
- 角色权限查询：当前席位权限集合
- 租户隔离共享资源：自选股（watchlist）、告警规则（alert_rules）按租户隔离读写
  —— 与前端实时页的 /api/watchlist 打通，使自选真正按租户隔离（而非全局单列表）
"""
from flask import Blueprint, jsonify, request

from fund_estimation_system.data_fetcher.tenant_service import (
    get_tenant_service, ROLE_NAMES, ROLE_PERMISSIONS,
)

bp = Blueprint("tenant", __name__)

# 默认演示席位（前端无登录态时使用的身份；真实部署应由 auth 网关注入 X-Seat-Id）
DEFAULT_SEAT = "admin-01"
DEFAULT_TENANT = "demo"


def _seat():
    """解析当前请求身份（演示态取默认 admin；预留从 Header 注入真实席位）。"""
    return (request.headers.get("X-Seat-Id")
            or (request.json or {}).get("seat_id")
            or request.args.get("seat_id")
            or DEFAULT_SEAT)


def _tenant():
    body_tenant = None
    if request.method in ("POST", "PUT", "PATCH", "DELETE") and request.is_json:
        body_tenant = (request.json or {}).get("tenant_id")
    return (request.headers.get("X-Tenant-Id")
            or body_tenant
            or request.args.get("tenant_id")
            or DEFAULT_TENANT)


@bp.route("/api/tenant/roles")
def api_tenant_roles():
    """可用角色与权限定义（供前端渲染权限矩阵）。"""
    return jsonify({
        "roles": [{"id": k, "name": v} for k, v in ROLE_NAMES.items()],
        "permissions": {k: sorted(v) for k, v in ROLE_PERMISSIONS.items()},
    })


@bp.route("/api/tenant/seats", methods=["GET", "POST", "DELETE"])
def api_tenant_seats():
    """席位管理（REQ-06：多用户/权限）。"""
    svc = get_tenant_service()
    if request.method == "GET":
        return jsonify({"tenant_id": _tenant(), "seats": svc.list_seats(_tenant())})
    if request.method == "POST":
        d = request.json or {}
        seat_id = d.get("seat_id", "").strip()
        role = d.get("role", "")
        name = d.get("name", "")
        if not seat_id:
            return jsonify({"success": False, "reason": "seat_id 必填"}), 400
        r = svc.add_seat(seat_id, role, name=name, tenant_id=_tenant())
        if not r["success"]:
            return jsonify(r), 400
        return jsonify(r)
    # DELETE
    seat_id = (request.json or {}).get("seat_id") or request.args.get("seat_id")
    if not seat_id:
        return jsonify({"success": False, "reason": "seat_id 必填"}), 400
    return jsonify(svc.remove_seat(seat_id, tenant_id=_tenant()))


@bp.route("/api/tenant/permission", methods=["GET"])
def api_tenant_permission():
    """查询某席位是否拥有某权限（REQ-06 权限隔离校验）。"""
    svc = get_tenant_service()
    seat_id = request.args.get("seat_id") or _seat()
    perm = request.args.get("perm", "")
    tenant = _tenant()
    return jsonify({
        "seat_id": seat_id,
        "tenant_id": tenant,
        "seat": svc.get_seat(seat_id, tenant),
        "has_permission": svc.has_permission(seat_id, perm, tenant) if perm else None,
        "permissions": svc.permissions_of(seat_id, tenant),
    })


@bp.route("/api/tenant/watchlist", methods=["GET", "POST", "DELETE"])
def api_tenant_watchlist():
    """租户隔离自选股（REQ-06：数据按租户隔离）。

    与实时页 /api/watchlist 保持兼容的接口契约：
      GET  -> {groups:{default:[...]}}
      POST -> {code}  加入自选
      DELETE -> ?code=xxx&group=default  移除
    """
    svc = get_tenant_service()
    tenant = _tenant()
    group = request.args.get("group") or (request.json or {}).get("group") or "default"
    if request.method == "GET":
        return jsonify({"tenant_id": tenant, "groups": {
            group: svc.get_watchlist(tenant, group),
        }})
    if request.method == "POST":
        code = (request.json or {}).get("code", "").strip()
        if not code:
            return jsonify({"success": False, "reason": "code 必填"}), 400
        codes = svc.get_watchlist(tenant, group)
        if code not in codes:
            codes.append(code)
        svc.set_watchlist(codes, tenant, group)
        return jsonify({"success": True, "group": group, "codes": codes})
    # DELETE
    code = (request.json or {}).get("code") or request.args.get("code")
    if not code:
        return jsonify({"success": False, "reason": "code 必填"}), 400
    codes = [c for c in svc.get_watchlist(tenant, group) if c != code]
    svc.set_watchlist(codes, tenant, group)
    return jsonify({"success": True, "group": group, "codes": codes})


@bp.route("/api/tenant/alert_rules", methods=["GET", "POST", "DELETE"])
def api_tenant_alert_rules():
    """租户隔离告警规则（REQ-06：告警规则按租户隔离，不同机构互不可见）。"""
    svc = get_tenant_service()
    tenant = _tenant()
    if request.method == "GET":
        rules = svc.get_alert_rules(tenant)
        # 列表化（dict 形式便于前端映射）
        return jsonify({"tenant_id": tenant, "rules": [
            dict(v, id=k) for k, v in rules.items()
        ]})
    if request.method == "POST":
        rule = request.json or {}
        rid = svc.set_alert_rule(rule, tenant)
        return jsonify({"success": True, "id": rid})
    # DELETE
    rid = (request.json or {}).get("id") or request.args.get("id")
    if not rid:
        return jsonify({"success": False, "reason": "id 必填"}), 400
    rules = svc.get_alert_rules(tenant)
    if rid in rules:
        del rules[rid]
        svc.set_alert_rule({"id": rid, "_deleted": True}, tenant)
        # 真正删除：重写规则映射（set_alert_rule 会重新写入，故直接操作 _data）
        svc._data["tenants"][tenant].setdefault("alert_rules", {}).pop(rid, None)
        svc._save()
        return jsonify({"success": True})
    return jsonify({"success": False, "reason": "规则不存在"})


@bp.route("/tenant")
def tenant_page():
    """多租户 / 权限管理页（REQ-06 前端入口）。"""
    from flask import render_template
    return render_template("tenant.html")
