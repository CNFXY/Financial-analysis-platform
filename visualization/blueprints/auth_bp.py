# -*- coding: utf-8 -*-
"""认证域路由：注册 / 登录 / 刷新 / 当前用户。

签发标准 JWT（access + refresh），供前端在 Authorization: Bearer <token> 中使用。
计费身份与登录用户强绑定（见 core/billing_guard）。
"""
from flask import Blueprint, request, jsonify

from fund_estimation_system.models.database import SessionLocal
from fund_estimation_system.models import User
from fund_estimation_system.core.auth import generate_tokens, verify_token, validate_password_strength
from fund_estimation_system.core.rate_limiter import rate_limit, get_client_ip
import fund_estimation_system.config as config

bp = Blueprint("auth", __name__, url_prefix="/api/auth")


def _json(success, data=None, error=None, status=200):
    return jsonify({"success": success, "data": data, "error": error}), status


@bp.route("/register", methods=["POST"])
@rate_limit(max_requests=config.RATE_LIMIT_REGISTER_PER_MIN, window_seconds=60,
            key_prefix="register")
def api_register():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    email = (data.get("email") or "").strip()
    password = data.get("password") or ""
    if not username or not email or not password:
        return _json(False, error="用户名/邮箱/密码均为必填", status=400)
    ok, reason = validate_password_strength(password)
    if not ok:
        return _json(False, error=reason, status=400)
    if "@" not in email:
        return _json(False, error="邮箱格式不正确", status=400)

    db = SessionLocal()
    try:
        if db.query(User).filter((User.username == username) | (User.email == email)).first():
            return _json(False, error="用户名或邮箱已存在", status=409)
        user = User.create(username=username, email=email, password=password, role="user")
        db.add(user)
        db.commit()
        db.refresh(user)
        tokens = generate_tokens(user.id, user.username, user.role, user.tenant_id)
        return _json(True, {"user": user.to_dict(), **tokens}, status=201)
    except Exception as e:
        db.rollback()
        return _json(False, error=f"注册失败：{e}", status=500)
    finally:
        db.close()


@bp.route("/login", methods=["POST"])
@rate_limit(max_requests=config.RATE_LIMIT_LOGIN_PER_MIN, window_seconds=60,
            key_prefix="login",
            key_func=lambda r: (r.get_json(silent=True) or {}).get("username")
            or (r.get_json(silent=True) or {}).get("email") or "")
def api_login():
    data = request.get_json(silent=True) or {}
    ident = (data.get("username") or data.get("email") or "").strip()
    password = data.get("password") or ""
    if not ident or not password:
        return _json(False, error="用户名/邮箱与密码均为必填", status=400)

    db = SessionLocal()
    try:
        user = db.query(User).filter(
            (User.username == ident) | (User.email == ident)).first()
        if not user or not user.check_password(password):
            return _json(False, error="用户名或密码错误", status=401)
        if not user.is_active:
            return _json(False, error="账户已禁用", status=403)
        user.last_login = __import__("datetime").datetime.utcnow()
        db.commit()
        tokens = generate_tokens(user.id, user.username, user.role, user.tenant_id)
        return _json(True, {"user": user.to_dict(), **tokens})
    finally:
        db.close()


@bp.route("/refresh", methods=["POST"])
def api_refresh():
    data = request.get_json(silent=True) or {}
    rt = data.get("refresh_token")
    if not rt:
        return _json(False, error="缺少 refresh_token", status=400)
    payload = verify_token(rt, token_type="refresh")
    if not payload:
        return _json(False, error="refresh_token 无效或已过期", status=401)
    db = SessionLocal()
    try:
        user = db.get(User, payload.get("sub"))
        if not user or not user.is_active:
            return _json(False, error="用户不存在或已禁用", status=401)
        tokens = generate_tokens(user.id, user.username, user.role, user.tenant_id)
        return _json(True, tokens)
    finally:
        db.close()


@bp.route("/me", methods=["GET"])
def api_me():
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return _json(False, error="未授权", status=401)
    payload = verify_token(auth[7:], token_type="access")
    if not payload:
        return _json(False, error="未授权或 token 已过期", status=401)
    db = SessionLocal()
    try:
        user = db.get(User, payload.get("sub"))
        if not user:
            return _json(False, error="用户不存在", status=401)
        return _json(True, user.to_dict())
    finally:
        db.close()


@bp.route("/change-password", methods=["POST"])
def api_change_password():
    """已登录用户修改密码（需校验旧密码 + 新密码强度策略）。"""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return _json(False, error="未授权", status=401)
    payload = verify_token(auth[7:], token_type="access")
    if not payload:
        return _json(False, error="未授权或 token 已过期", status=401)

    data = request.get_json(silent=True) or {}
    old_pwd = data.get("old_password") or ""
    new_pwd = data.get("new_password") or ""
    if not old_pwd or not new_pwd:
        return _json(False, error="旧密码与新密码均为必填", status=400)

    ok, reason = validate_password_strength(new_pwd)
    if not ok:
        return _json(False, error=reason, status=400)
    if new_pwd == old_pwd:
        return _json(False, error="新密码不能与旧密码相同", status=400)

    db = SessionLocal()
    try:
        user = db.get(User, payload.get("sub"))
        if not user:
            return _json(False, error="用户不存在", status=401)
        if not user.check_password(old_pwd):
            return _json(False, error="旧密码错误", status=400)
        user.set_password(new_pwd)
        db.commit()
        return _json(True, {"message": "密码已更新"})
    except Exception as e:
        db.rollback()
        return _json(False, error=f"修改失败：{e}", status=500)
    finally:
        db.close()
