# -*- coding: utf-8 -*-
"""支付与订阅域路由（REQ-16 商业化支付 + REQ-11 套餐模型 + REQ-12 配额）。

安全修复（P0-2）：计费身份强制绑定登录用户，所有会变动状态的接口（me/check/
trial/order/orders/activate）必须携带有效 Bearer token，杜绝匿名绕过付费墙。

提供：
- GET  /api/billing/plans                套餐列表（公开，供前端 pricing 页）
- GET  /api/billing/me                   当前登录用户的有效订阅 + 配额状态
- POST /api/billing/check                权限/配额预校验（需登录）
- POST /api/billing/trial                开启试用（需登录）
- POST /api/billing/order                创建订单（需登录）
- GET  /api/billing/order/<id>           查询订单（需登录）
- GET  /api/billing/orders               订单列表（需登录）
- POST /api/billing/notify/alipay        支付宝异步通知（公开回调）
- POST /api/billing/notify/wechat        微信异步通知（公开回调，XML）
- GET  /api/billing/return               支付宝同步回跳
- POST /api/billing/activate             商务手动激活（机构版，需 admin）
- GET  /pricing                          公开定价页
- GET  /billing                          已登录账单中心
- GET  /billing/return                   支付完成回跳页
"""
import os
import json
from datetime import datetime
from flask import Blueprint, jsonify, request, render_template, current_app, abort, g

from fund_estimation_system import config
from fund_estimation_system.core.auth import verify_token
from fund_estimation_system.data_fetcher.payment_service import (
    get_payment_service, PLANS,
)

bp = Blueprint("billing", __name__)


def _scope_from_auth():
    """从 Bearer token 解析登录用户，返回 ('user', user_id)。

    未登录返回 None；调用方应据此返回 401。计费身份必须与登录用户一致，
    否则任何人可用 X-Tenant-Id 头冒充租户绕过付费墙。
    """
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    payload = verify_token(auth[7:], token_type="access")
    if not payload:
        return None
    g.user_id = payload.get("sub")
    g.user_role = payload.get("role")
    g.username = payload.get("username")
    return ("user", g.user_id)


def _require_scope():
    scope = _scope_from_auth()
    if not scope:
        return None, (jsonify({"success": False, "code": 401001,
                               "message": "未授权，请先登录", "data": None}), 401)
    return scope, None


# ============== 套餐 / 订阅 ==============
@bp.route("/api/billing/plans")
def api_billing_plans():
    """套餐列表（公开）。"""
    return jsonify({
        "mode": os.environ.get("PAYMENT_MODE", "sandbox"),
        "plans": get_payment_service().list_plans(),
    })


@bp.route("/api/billing/me")
def api_billing_me():
    """当前登录用户的有效订阅 + 配额状态 + 套餐信息。"""
    scope, err = _require_scope()
    if err:
        return err
    svc = get_payment_service()
    sub = svc.get_effective_subscription(scope[1])
    plan = svc.get_plan(sub["plan"])
    return jsonify({
        "scope_type": sub["scope_type"],
        "scope_id": sub["scope_id"],
        "subscription": sub,
        "plan": plan,
        "quota": svc.get_quota_status(sub["scope_type"], sub["scope_id"]),
        "is_active": svc.is_active(sub),
    })


@bp.route("/api/billing/check", methods=["POST"])
def api_billing_check():
    """权限/配额预校验：业务调用方在关键接口前调用（需登录）。"""
    scope, err = _require_scope()
    if err:
        return err
    data = request.json or {}
    feature = data.get("feature")
    quota_key = data.get("quota_key")
    n = int(data.get("n", 1))
    svc = get_payment_service()
    sub = svc.get_effective_subscription(scope[1])
    if feature and not svc.has_feature(feature, sub):
        plan_now = svc.get_plan(sub["plan"]) or {"name": "免费版", "code": "free"}
        return jsonify({
            "allowed": False, "reason": "feature_locked",
            "message": f"当前套餐({plan_now['name']})未开放该能力",
            "current_plan": plan_now["code"], "upgrade_url": "/pricing",
        }), 403
    if quota_key:
        ok, info = svc.consume_quota(quota_key, sub["scope_type"], sub["scope_id"], n=n)
        return jsonify({"allowed": ok, "quota": info}), (200 if ok else 429)
    return jsonify({"allowed": True})


@bp.route("/api/billing/trial", methods=["POST"])
def api_billing_trial():
    """开启试用：7 天 Pro / 14 天 Enterprise（需登录）。"""
    scope, err = _require_scope()
    if err:
        return err
    data = request.json or {}
    plan_code = data.get("plan")
    return jsonify(get_payment_service().start_trial(plan_code, scope[0], scope[1]))


# ============== 订单 ==============
@bp.route("/api/billing/order", methods=["POST"])
def api_billing_order():
    """创建订单（未支付，需登录）。订阅落在当前用户 scope。"""
    scope, err = _require_scope()
    if err:
        return err
    data = request.json or {}
    plan_code = data.get("plan")
    channel = data.get("channel", "alipay_web")
    extra = data.get("extra", {})
    return jsonify(get_payment_service().create_order(
        plan_code, channel, scope[0], scope[1], user_id=scope[1], extra=extra
    ))


@bp.route("/api/billing/order/<order_id>")
def api_billing_order_get(order_id):
    scope, err = _require_scope()
    if err:
        return err
    o = get_payment_service().get_order(order_id)
    if not o:
        return jsonify({"error": "订单不存在"}), 404
    return jsonify(o)


@bp.route("/api/billing/orders")
def api_billing_orders():
    scope, err = _require_scope()
    if err:
        return err
    return jsonify({
        "scope_type": scope[0],
        "scope_id": scope[1],
        "orders": get_payment_service().list_orders(scope[0], scope[1]),
    })


# ============== 支付回调 ==============
@bp.route("/api/billing/notify/alipay", methods=["POST"])
def api_billing_notify_alipay():
    """支付宝异步通知（POST application/x-www-form-urlencoded）。"""
    params = request.form.to_dict() if request.form else (request.json or {})
    current_app.logger.info(f"[billing] 支付宝回调: out_trade_no={params.get('out_trade_no')} status={params.get('trade_status')}")
    result = get_payment_service().handle_alipay_notify(params)
    return ("success" if result.get("success") else "fail"), 200


@bp.route("/api/billing/notify/wechat", methods=["POST"])
def api_billing_notify_wechat():
    """微信异步通知（XML 格式）。"""
    raw = request.data.decode("utf-8", errors="ignore")
    current_app.logger.info(f"[billing] 微信回调 raw={raw[:200]}")
    result = get_payment_service().handle_wechat_notify(raw)
    if result.get("return_code") == "SUCCESS":
        return ('<xml><return_code><![CDATA[SUCCESS]]></return_code>'
                '<return_msg><![CDATA[OK]]></return_msg></xml>'), 200
    return ('<xml><return_code><![CDATA[FAIL]]></return_code>'
            f'<return_msg><![CDATA[{result.get("reason","ERR")}]]></return_msg></xml>'), 200


@bp.route("/api/billing/return")
def api_billing_return():
    """支付宝同步回跳页（仅展示，不作入账依据）。"""
    params = request.args.to_dict()
    verified = True
    if config.PAYMENT_MODE == "production":
        verified = get_payment_service().verify_alipay_return(params)
    return render_template("billing_return.html", params=params, verified=verified)


# ============== 商务手动激活（需 admin） ==============
@bp.route("/api/billing/activate", methods=["POST"])
def api_billing_activate():
    """商务手动激活（机构版线下合同 → 财务确认 → 一键激活）。

    仅限 admin；订阅落在请求指定的租户 scope（tenant）。
    """
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return jsonify({"success": False, "code": 401001, "message": "未授权"}), 401
    payload = verify_token(auth[7:], token_type="access")
    if not payload or payload.get("role") != "admin":
        return jsonify({"success": False, "code": 403003, "message": "权限不足（需管理员）"}), 403
    data = request.json or {}
    tenant_id = data.get("tenant_id")
    if not tenant_id:
        return jsonify({"success": False, "reason": "缺少 tenant_id"}), 400
    return jsonify(get_payment_service().manual_activate(
        scope_type="tenant", scope_id=tenant_id,
        plan_code=data.get("plan"),
        operator=payload.get("username", "admin"),
        note=data.get("note", ""),
    ))


# ============== 前端页面 ==============
@bp.route("/pricing")
def pricing_page():
    return render_template("pricing.html", plans=get_payment_service().list_plans())


@bp.route("/billing")
def billing_page():
    return render_template("billing.html")


# ============== 沙箱模拟支付确认页 ==============
@bp.route("/sandbox/pay-confirm")
def sandbox_pay_confirm():
    if config.PAYMENT_MODE == "production":
        abort(403)
    order_id = request.args.get("order_id")
    ch = request.args.get("ch", "wechat")
    svc = get_payment_service()
    o = svc.get_order(order_id) if order_id else None
    if not o:
        return f'<h2 style="font-family:sans-serif;padding:40px;">订单不存在或已失效：{order_id}</h2>', 404
    return render_template(
        "sandbox_pay_confirm.html",
        order=o, channel=ch,
        amount=f"{o['amount_cents']/100:.2f}",
        plan_name=o["plan_name"],
    )


@bp.route("/sandbox/pay-confirm", methods=["POST"])
def sandbox_pay_confirm_post():
    if config.PAYMENT_MODE == "production":
        abort(403)
    data = request.form.to_dict() if request.form else (request.json or {})
    order_id = data.get("order_id")
    ch = data.get("ch", "wechat")
    svc = get_payment_service()
    o = svc.get_order(order_id) if order_id else None
    if not o:
        return jsonify({"success": False, "reason": "订单不存在或已失效"}), 404
    if o["status"] == "paid":
        return jsonify({"success": True, "already_paid": True, "order_id": order_id})
    if ch == "alipay":
        result = svc.handle_alipay_notify({
            "out_trade_no": order_id,
            "trade_status": "TRADE_SUCCESS",
            "trade_no": "SANDBOXALI" + order_id,
        })
    else:
        result = svc.handle_wechat_notify({
            "out_trade_no": order_id,
            "result_code": "SUCCESS",
            "transaction_id": "SANDBOXWX" + order_id,
        })
    if result.get("success"):
        return jsonify({"success": True, "order_id": order_id})
    return jsonify({"success": False, "reason": result.get("reason", "处理失败")}), 400
