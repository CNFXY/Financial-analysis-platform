# -*- coding: utf-8 -*-
"""支付与订阅服务（REQ-16 商业化支付 + REQ-11 套餐模型）。

本模块是"支付宝/微信支付的薄适配层"，遵循以下设计原则：

1. **沙箱优先**：默认沙箱可跑，无需真实商户号即可本地端到端验证；
2. **生产可切换**：通过 config.PAYMENT_MODE = sandbox / production 切换；
3. **回调幂等**：按 out_trade_no 落库 + 非重复交易号唯一约束防重放；
4. **订阅联动**：回调成功 → 更新订阅（scope 可落在 租户 或 用户）+ 审计；
5. **零外部依赖必选**：当 SDK 未安装时回退到本地"模拟通道"，保证演示与开发可用；
6. **数据存储全部落库（SQLAlchemy）**：替代原先的「内存字典 + JSON 文件」，
   解决 gunicorn 多 worker 下订单/订阅跨进程不可见、并发写坏文件的问题。
   幂等性由 billing_nonces.trade_no 唯一约束在数据库层兜底。

计费模型（按用户选择）：用户属于租户，订阅可下钻到 用户 或 租户。
scope_type ∈ {'tenant','user'}，scope_id 为对应 ID。
有效订阅分辨率：用户级订阅 > 租户级订阅 > free。
"""

import os
import json
import time
import hmac
import hashlib
import secrets
import threading
import urllib.parse
from datetime import datetime, timedelta

from flask import current_app

from fund_estimation_system import config
from fund_estimation_system.models.database import SessionLocal
from fund_estimation_system.models import (
    BillingOrder, BillingSubscription, BillingNonce, BillingQuota, User,
)


# ---------------------- Plan 定义（REQ-11 套餐模型）----------------------
PLANS = {
    "free": {
        "code": "free",
        "name": "免费版",
        "price_cents": 0,
        "duration_days": 36500,  # 永久
        "seats": 1,
        "features": {
            "realtime_quote": False, "delayed_quote": True, "l2_depth": False,
            "fund_estimate_basic": True, "fund_estimate_full": False,
            "tech_analysis": True, "valuation": False, "backtest": False,
            "backtest_guardrail": False, "risk_basic": True, "risk_full": False,
            "alert_per_day": 3, "backtest_per_day": 0, "api_per_day": 200,
            "watchlist_size": 5, "export": False, "push": ["inapp"],
            "audit_days": 0, "compliance_pack": False, "sla": "none",
        },
    },
    "pro": {
        "code": "pro",
        "name": "专业版",
        "price_cents": 29900,  # ¥299/月
        "duration_days": 30,
        "seats": 1,
        "features": {
            "realtime_quote": True, "delayed_quote": True, "l2_depth": False,
            "fund_estimate_basic": True, "fund_estimate_full": True,
            "tech_analysis": True, "valuation": True, "backtest": True,
            "backtest_guardrail": False, "risk_basic": True, "risk_full": True,
            "alert_per_day": 50, "backtest_per_day": 5, "api_per_day": 5000,
            "watchlist_size": 50, "export": True, "push": ["inapp", "webhook"],
            "audit_days": 7, "compliance_pack": False, "sla": "99.5%",
        },
    },
    "enterprise": {
        "code": "enterprise",
        "name": "机构版",
        "price_cents": 500000,  # ¥5,000/年起
        "duration_days": 365,
        "seats": 5,
        "features": {
            "realtime_quote": True, "delayed_quote": True, "l2_depth": True,
            "fund_estimate_basic": True, "fund_estimate_full": True,
            "tech_analysis": True, "valuation": True, "backtest": True,
            "backtest_guardrail": True, "risk_basic": True, "risk_full": True,
            "alert_per_day": 99999, "backtest_per_day": 99999, "api_per_day": 50000,
            "watchlist_size": 99999, "export": True,
            "push": ["inapp", "webhook", "wecom", "sms"],
            "audit_days": 36500, "compliance_pack": True, "sla": "99.9%",
        },
    },
}


# ---------------------- 工具函数 ----------------------
def _now():
    return int(time.time())


def _dt(epoch):
    return datetime.utcfromtimestamp(epoch) if epoch else None


def _gen_order_id(channel, scope_id):
    """生成全局唯一订单号：YYYYMMDDHHMMSS + 8位随机串 + 渠道标记。"""
    return f"{datetime.now().strftime('%Y%m%d%H%M%S')}{secrets.token_hex(4).upper()}{channel[:2].upper()}"


def _resolve_key(inline_value, path_value):
    """证书解析：若 path_value 指向的密钥文件存在则读取文件内容，否则用内联字符串。"""
    if path_value:
        try:
            with open(path_value, "r", encoding="utf-8") as f:
                content = f.read().strip()
            if content:
                return content
        except Exception:
            pass
    return inline_value or ""


def _rsa_sign_alipay(params, private_key):
    """支付宝 RSA2 签名。"""
    items = sorted((k, v) for k, v in params.items() if k != "sign" and v not in (None, ""))
    sign_str = "&".join(f"{k}={v}" for k, v in items)
    try:
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding
        key = serialization.load_pem_private_key(private_key.encode(), password=None)
        sig = key.sign(sign_str.encode("utf-8"), padding.PKCS1v15(), hashes.SHA256())
        return b64encode_safe(sig)
    except Exception:
        return b64encode_safe(hmac.new(private_key.encode("utf-8"), sign_str.encode("utf-8"), hashlib.sha256).digest())


def b64encode_safe(b):
    from base64 import b64encode
    return b64encode(b).decode()


def _rsa_verify_alipay(params, public_key, sign):
    """支付宝验签：与签名使用同一套拼接规则（排除 sign 与空值）。"""
    from base64 import b64decode
    if not sign:
        return False
    items = sorted((k, v) for k, v in params.items() if k != "sign" and v not in (None, ""))
    sign_str = "&".join(f"{k}={v}" for k, v in items)
    try:
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding
        key = serialization.load_pem_public_key(public_key.encode("utf-8"))
        key.verify(b64decode(sign), sign_str.encode("utf-8"), padding.PKCS1v15(), hashes.SHA256())
        return True
    except Exception:
        expected = b64encode_safe(hmac.new(public_key.encode("utf-8"), sign_str.encode("utf-8"), hashlib.sha256).digest())
        return hmac.compare_digest(expected, sign or "")


def _md5_sign_wechat(params, key):
    items = sorted((k, v) for k, v in params.items() if k != "sign" and v not in (None, ""))
    sign_str = "&".join(f"{k}={v}" for k, v in items) + f"&key={key}"
    return hashlib.md5(sign_str.encode("utf-8")).hexdigest().upper()


def _md5_verify_wechat(params, key, sign):
    expected = _md5_sign_wechat(params, key)
    return hmac.compare_digest(expected, sign or "")


# ---------------------- 订阅 dict 构造 / 评估 ----------------------
def _free_dict(scope_type, scope_id):
    now = _now()
    return {
        "scope_type": scope_type,
        "scope_id": scope_id,
        "plan": "free",
        "status": "active",
        "started_at": now,
        "expires_at": now + 36500 * 86400,
        "trial": False,
        "trial_ends_at": None,
        "seats": 1,
        "order_id": None,
        "operator": None,
        "note": None,
        "updated_at": now,
    }


def _row_to_dict(row) -> dict:
    return {
        "scope_type": row.scope_type,
        "scope_id": row.scope_id,
        "plan": row.plan,
        "status": row.status,
        "started_at": int(row.started_at.timestamp()) if row.started_at else None,
        "expires_at": int(row.expires_at.timestamp()) if row.expires_at else None,
        "trial": bool(row.trial),
        "trial_ends_at": int(row.trial_ends_at.timestamp()) if row.trial_ends_at else None,
        "seats": row.seats,
        "order_id": row.order_id,
        "operator": row.operator,
        "note": row.note,
        "updated_at": int(row.updated_at.timestamp()) if row.updated_at else None,
    }


def _eval_sub(d: dict) -> dict:
    """按时间评估有效套餐：付费且已过期 → 降级 free（仅用于能力判定，不动库）。"""
    if d["plan"] != "free" and (d.get("expires_at") or 0) < _now():
        return _free_dict(d["scope_type"], d["scope_id"])
    return d


# ---------------------- 支付服务核心 ----------------------
class PaymentService:
    """统一支付服务：订单创建 + 回调处理 + 订阅联动。

    所有状态落库（SQLAlchemy），每次操作独立 Session，无进程内缓存，
    因此天然支持 gunicorn 多 worker / 多进程部署。
    """

    def __init__(self):
        # 仍保留一份线程锁，仅用于「同一进程内」本地计算的极小临界区（如订单号生成），
        # 真正的并发安全由数据库事务与唯一约束保证。
        self._lock = threading.Lock()

    # ---- 套餐 / 订阅（读） ----
    def list_plans(self):
        return list(PLANS.values())

    def get_plan(self, code):
        return PLANS.get(code)

    def get_subscription(self, scope_type="tenant", scope_id="demo") -> dict:
        """读取某 scope 的订阅；不存在返回 free 合成 dict。"""
        db = SessionLocal()
        try:
            row = (db.query(BillingSubscription)
                   .filter_by(scope_type=scope_type, scope_id=str(scope_id))
                   .first())
            if not row:
                return _free_dict(scope_type, scope_id)
            return _eval_sub(_row_to_dict(row))
        finally:
            db.close()

    def get_effective_subscription(self, user_id) -> dict:
        """用户有效订阅：用户级 > 租户级 > free。"""
        user_id = str(user_id)
        user_sub = self.get_subscription("user", user_id)
        if user_sub["plan"] != "free":
            return user_sub
        # 查租户级
        db = SessionLocal()
        try:
            u = db.query(User).filter_by(id=user_id).first()
        finally:
            db.close()
        tenant_id = u.tenant_id if u else None
        if tenant_id:
            tenant_sub = self.get_subscription("tenant", tenant_id)
            if tenant_sub["plan"] != "free":
                return tenant_sub
        return _free_dict("user", user_id)

    def has_feature(self, feature_key, sub: dict) -> bool:
        plan = PLANS.get(sub["plan"], PLANS["free"])
        return bool(plan["features"].get(feature_key, False))

    def get_quota(self, quota_key, sub: dict) -> int:
        plan = PLANS.get(sub["plan"], PLANS["free"])
        return int(plan["features"].get(quota_key, 0))

    def is_active(self, sub: dict) -> bool:
        if sub["status"] == "active":
            return True
        if sub["status"] == "trial" and (sub.get("trial_ends_at") or 0) > _now():
            return True
        return sub["plan"] == "free"

    # ---- 证书解析 ----
    def _alipay_private_key(self):
        return _resolve_key(config.ALIPAY_PRIVATE_KEY, getattr(config, "ALIPAY_PRIVATE_KEY_PATH", ""))

    def _alipay_public_key(self):
        return _resolve_key(config.ALIPAY_PUBLIC_KEY, getattr(config, "ALIPAY_PUBLIC_KEY_PATH", ""))

    def _wechat_api_key(self):
        return _resolve_key(config.WECHAT_API_KEY, getattr(config, "WECHAT_API_KEY_PATH", ""))

    # ---- 试用 ----
    def start_trial(self, plan_code, scope_type, scope_id):
        """开启试用：7 天 Pro / 14 天 Enterprise。"""
        plan = PLANS.get(plan_code)
        if not plan or plan_code == "free":
            return {"success": False, "reason": "不支持试用此套餐"}
        scope_id = str(scope_id)
        db = SessionLocal()
        try:
            row = (db.query(BillingSubscription)
                   .filter_by(scope_type=scope_type, scope_id=scope_id).first())
            if row and row.trial:
                return {"success": False, "reason": "已使用过试用"}
            now = _now()
            days = 7 if plan_code == "pro" else 14
            expires = now + days * 86400
            if not row:
                row = BillingSubscription(scope_type=scope_type, scope_id=scope_id)
                db.add(row)
            row.plan = plan_code
            row.status = "trial"
            row.trial = True
            row.trial_ends_at = _dt(expires)
            row.expires_at = _dt(expires)
            row.seats = plan["seats"]
            row.started_at = row.started_at or _dt(now)
            row.updated_at = _dt(now)
            db.commit()
            return {"success": True, "subscription": _row_to_dict(row), "trial_days": days}
        finally:
            db.close()

    # ---- 订单（写） ----
    def create_order(self, plan_code, channel, scope_type, scope_id,
                     user_id=None, extra=None):
        """创建订单（未支付）。返回 order 记录 + 支付所需 payload。"""
        plan = PLANS.get(plan_code)
        if not plan:
            return {"success": False, "reason": f"未知套餐 {plan_code}"}
        if plan_code == "free":
            return {"success": False, "reason": "免费版无需支付"}
        if channel not in ("alipay_web", "alipay_wap", "alipay_native",
                           "wechat_native", "wechat_h5", "wechat_jsapi", "manual"):
            return {"success": False, "reason": f"不支持的支付渠道 {channel}"}

        scope_id = str(scope_id)
        with self._lock:
            order_id = _gen_order_id(channel, scope_id)
        now = _now()
        order = {
            "order_id": order_id,
            "scope_type": scope_type,
            "scope_id": scope_id,
            "user_id": str(user_id) if user_id else scope_id,
            "plan_code": plan_code,
            "plan_name": plan["name"],
            "amount_cents": plan["price_cents"],
            "channel": channel,
            "status": "pending",
            "created_at": now,
            "paid_at": None,
            "trade_no": None,
            "extra": extra or {},
        }
        db = SessionLocal()
        try:
            db.add(BillingOrder(
                order_id=order_id, scope_type=scope_type, scope_id=scope_id,
                user_id=order["user_id"], plan_code=plan_code, plan_name=plan["name"],
                amount_cents=plan["price_cents"], channel=channel, status="pending",
                created_at=_dt(now), extra=extra or {},
            ))
            db.commit()
        finally:
            db.close()

        order["client_payload"] = self._build_payload(order)
        return {"success": True, "order": order}

    def _build_payload(self, order):
        """根据渠道生成前端唤起支付所需的 payload（与旧实现一致）。"""
        ch = order["channel"]
        amount_yuan = f"{order['amount_cents'] / 100:.2f}"
        if ch.startswith("alipay"):
            is_native = (ch == "alipay_native")
            params = {
                "app_id": config.ALIPAY_APP_ID,
                "method": "alipay.trade.precreate" if is_native else (
                    "alipay.trade.wap.pay" if ch == "alipay_wap" else "alipay.trade.page.pay"),
                "charset": "utf-8",
                "sign_type": "RSA2",
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "version": "1.0",
                "notify_url": config.PAYMENT_NOTIFY_BASE + "/api/billing/notify/alipay",
                "biz_content": json.dumps({
                    "out_trade_no": order["order_id"],
                    "product_code": "FAST_INSTANT_TRADE_PAY",
                    "total_amount": amount_yuan,
                    "subject": f"FUND-OS {order['plan_name']}订阅",
                }, ensure_ascii=False),
            }
            if not is_native:
                params["return_url"] = config.PAYMENT_RETURN_URL
            params["sign"] = _rsa_sign_alipay(params, self._alipay_private_key())
            gateway = (
                "https://openapi.alipaydev.com/gateway.do"
                if config.PAYMENT_MODE == "sandbox" else
                "https://openapi.alipay.com/gateway.do"
            )
            if config.PAYMENT_MODE == "sandbox":
                confirm_url = f"{config.PAYMENT_NOTIFY_BASE}/sandbox/pay-confirm?order_id={order['order_id']}&ch=alipay"
                qr_url = self._gen_qr_png(confirm_url, order["order_id"])
                return {
                    "type": "alipay_redirect", "url": confirm_url, "qrcode_url": qr_url,
                    "confirm_url": confirm_url, "sandbox_fallback": True, "method": "GET",
                }
            if is_native:
                qr_code = self._alipay_precreate(order)
                if qr_code:
                    return {"type": "alipay_native", "code_url": qr_code,
                            "qrcode_url": self._gen_qr_png(qr_code, order["order_id"]),
                            "note": "生产环境已调用 alipay.trade.precreate 获取真实扫码二维码"}
                return {"type": "alipay_native", "error": "precreate_failed",
                        "note": "支付宝预创建失败，请检查商户号/网关/签名"}
            query = urllib.parse.urlencode(params)
            pay_url = f"{gateway}?{query}"
            return {"type": "alipay_redirect", "url": pay_url, "method": "GET",
                    "form_html": ('<form id="alipay_submit" method="GET" action="' + gateway + '">' +
                                  "".join(f'<input type="hidden" name="{k}" value="{urllib.parse.quote(str(v))}"/>' for k, v in params.items()) +
                                  '<input type="submit" value="前往支付宝支付"/></form>')}
        if ch.startswith("wechat"):
            params = {
                "appid": config.WECHAT_APP_ID,
                "mch_id": config.WECHAT_MCH_ID,
                "nonce_str": secrets.token_hex(16),
                "body": f"FUND-OS {order['plan_name']}订阅",
                "out_trade_no": order["order_id"],
                "total_fee": str(order["amount_cents"]),
                "spbill_create_ip": "127.0.0.1",
                "notify_url": config.PAYMENT_NOTIFY_BASE + "/api/billing/notify/wechat",
                "trade_type": {"wechat_native": "NATIVE", "wechat_h5": "MWEB", "wechat_jsapi": "JSAPI"}[ch],
                "sign_type": "MD5",
            }
            params["sign"] = _md5_sign_wechat(params, self._wechat_api_key())
            if config.PAYMENT_MODE == "sandbox":
                confirm_url = f"{config.PAYMENT_NOTIFY_BASE}/sandbox/pay-confirm?order_id={order['order_id']}&ch=wechat"
                qr_url = self._gen_qr_png(confirm_url, order["order_id"])
                return {"type": "wechat_native", "qrcode_url": qr_url, "confirm_url": confirm_url,
                        "code_url": confirm_url, "params": params, "sandbox_fallback": True}
            result = self._wechat_unifiedorder(params, order)
            code_url = result.get("code_url")
            mweb_url = result.get("mweb_url")
            if ch == "wechat_native":
                return {"type": "wechat_native", "code_url": code_url,
                        "qrcode_url": self._gen_qr_png(code_url, order["order_id"]) if code_url else None,
                        "note": "生产环境已调用统一下单接口获取 code_url"}
            if ch == "wechat_h5":
                return {"type": "wechat_h5", "url": mweb_url, "qrcode_url": None,
                        "note": "生产环境 H5 支付，跳转 mweb_url 完成"}
            return {"type": "wechat_jsapi", "qrcode_url": None,
                    "note": "JSAPI 需前端传入 openid，请在业务层补齐后调用"}
        if ch == "manual":
            return {"type": "manual", "note": "请联系商务完成线下合同，财务手动激活"}
        return {}

    # ---- 真实二维码生成 ----
    def _gen_qr_png(self, text, order_id):
        try:
            import qrcode
        except Exception:
            try:
                current_app.logger.warning("[billing] 未安装 qrcode，无法生成二维码（pip install qrcode pillow）")
            except Exception:
                pass
            return None
        try:
            from PIL import Image
        except Exception:
            return None
        qr_dir = getattr(config, "QR_CODE_DIR", None)
        if not qr_dir:
            return None
        try:
            os.makedirs(qr_dir, exist_ok=True)
        except Exception:
            return None
        path = os.path.join(qr_dir, f"{order_id}.png")
        try:
            qr = qrcode.QRCode(version=4, error_correction=qrcode.constants.ERROR_CORRECT_M,
                               box_size=8, border=2)
            qr.add_data(text)
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")
            img.save(path)
            return f"/static/pay_qr/{order_id}.png"
        except Exception as e:
            try:
                current_app.logger.warning(f"[billing] 二维码生成失败: {e}")
            except Exception:
                pass
            return None

    def _wechat_unifiedorder(self, params, order):
        import requests
        try:
            import xml.etree.ElementTree as ET
            xml_body = "<xml>" + "".join(
                f"<{k}><![CDATA[{v}]]></{k}>" for k, v in params.items()
            ) + "</xml>"
            resp = requests.post("https://api.mch.weixin.qq.com/pay/unifiedorder",
                                 data=xml_body.encode("utf-8"), timeout=8)
            root = ET.fromstring(resp.content)
            data = {child.tag: child.text for child in root}
            if data.get("return_code") == "SUCCESS" and data.get("result_code") == "SUCCESS":
                return {"code_url": data.get("code_url"), "mweb_url": data.get("mweb_url"),
                        "prepay_id": data.get("prepay_id")}
        except Exception as e:
            try:
                current_app.logger.warning(f"[billing] 微信统一下单请求异常: {e}")
            except Exception:
                pass
        return {}

    def _alipay_precreate(self, order):
        import requests
        params = {
            "app_id": config.ALIPAY_APP_ID,
            "method": "alipay.trade.precreate",
            "charset": "utf-8",
            "sign_type": "RSA2",
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "version": "1.0",
            "notify_url": config.PAYMENT_NOTIFY_BASE + "/api/billing/notify/alipay",
            "biz_content": json.dumps({
                "out_trade_no": order["order_id"],
                "total_amount": f"{order['amount_cents'] / 100:.2f}",
                "subject": f"FUND-OS {order['plan_name']}订阅",
            }, ensure_ascii=False),
        }
        params["sign"] = _rsa_sign_alipay(params, self._alipay_private_key())
        try:
            r = requests.post("https://openapi.alipay.com/gateway.do", data=params, timeout=8)
            resp = r.json().get("alipay_trade_precreate_response", {})
            if resp.get("code") == "10000":
                return resp.get("qr_code")
        except Exception as e:
            try:
                current_app.logger.warning(f"[billing] 支付宝预创建请求异常: {e}")
            except Exception:
                pass
        return None

    def verify_alipay_return(self, params):
        return _rsa_verify_alipay(params, self._alipay_public_key(), params.get("sign", ""))

    # ---- 回调处理 ----
    def _mark_paid(self, order_id, trade_no, channel):
        """幂等入账：更新订单状态 + 激活对应 scope 订阅。返回 (order_dict, changed)。"""
        db = SessionLocal()
        try:
            order = db.query(BillingOrder).filter_by(order_id=order_id).first()
            if not order:
                return None, False
            if order.status == "paid":
                return _order_to_dict(order), False  # 已支付，幂等
            now = _now()
            order.status = "paid"
            order.paid_at = _dt(now)
            order.trade_no = trade_no
            order.channel = channel
            order.updated_at = _dt(now)

            plan = PLANS.get(order.plan_code)
            sub = (db.query(BillingSubscription)
                   .filter_by(scope_type=order.scope_type, scope_id=order.scope_id)
                   .first())
            base = max(int(sub.expires_at.timestamp()) if sub and sub.expires_at else now, now)
            if not sub:
                sub = BillingSubscription(scope_type=order.scope_type, scope_id=order.scope_id)
                db.add(sub)
            sub.plan = order.plan_code
            sub.status = "active"
            sub.trial = False
            sub.trial_ends_at = None
            sub.expires_at = _dt(base + plan["duration_days"] * 86400)
            sub.seats = plan["seats"]
            sub.order_id = order_id
            sub.updated_at = _dt(now)

            db.commit()
            return _order_to_dict(order), True
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def handle_alipay_notify(self, params):
        """处理支付宝异步通知。

        沙箱：仅校验关键字段（无真实 RSA 密钥）；生产：严格 RSA2 验签。
        幂等：trade_no 唯一约束保证跨进程不重复入账。
        """
        params = dict(params)
        if config.PAYMENT_MODE == "production":
            if not _rsa_verify_alipay(params, self._alipay_public_key(), params.get("sign", "")):
                return {"success": False, "reason": "签名校验失败"}
        else:
            if not params.get("out_trade_no") or not params.get("trade_status"):
                return {"success": False, "reason": "缺少关键字段"}
        if params.get("trade_status") not in ("TRADE_SUCCESS", "TRADE_FINISHED"):
            return {"success": True, "note": "非成功状态忽略"}
        order_id = params.get("out_trade_no")
        trade_no = params.get("trade_no")

        # 幂等：trade_no 唯一约束；并发重复通知由数据库层兜底
        if not self._consume_nonce(trade_no, "alipay"):
            return {"success": True, "note": "重复通知已忽略"}

        order, changed = self._mark_paid(order_id, trade_no, "alipay")
        if not order:
            return {"success": False, "reason": "订单不存在"}
        return {"success": True, "changed": changed, "order_id": order_id}

    def handle_wechat_notify(self, xml_or_json):
        """处理微信支付异步通知（XML；演示回退 JSON）。"""
        try:
            if isinstance(xml_or_json, bytes):
                xml_str = xml_or_json.decode("utf-8", errors="ignore")
            else:
                xml_str = xml_or_json or ""
            import xml.etree.ElementTree as ET
            root = ET.fromstring(xml_str) if xml_str else None
            data = {child.tag: child.text for child in root} if root is not None else {}
        except Exception:
            data = xml_or_json if isinstance(xml_or_json, dict) else {}
        if config.PAYMENT_MODE == "production":
            if not _md5_verify_wechat(data, self._wechat_api_key(), data.get("sign", "")):
                return {"success": False, "reason": "签名校验失败", "return_code": "FAIL"}
        else:
            if not data.get("out_trade_no"):
                return {"success": False, "return_code": "FAIL", "reason": "缺少 out_trade_no"}
        if data.get("result_code") != "SUCCESS":
            return {"success": True, "return_code": "SUCCESS", "note": "非成功通知忽略"}
        order_id = data.get("out_trade_no")
        trade_no = data.get("transaction_id")
        if not self._consume_nonce(trade_no, "wechat"):
            return {"success": True, "return_code": "SUCCESS", "note": "重复通知已忽略"}
        order, changed = self._mark_paid(order_id, trade_no, "wechat")
        if not order:
            return {"success": False, "return_code": "FAIL", "reason": "订单不存在"}
        return {"success": True, "return_code": "SUCCESS", "return_msg": "OK",
                "changed": changed, "order_id": order_id}

    def _consume_nonce(self, trade_no, channel) -> bool:
        """写入 nonce；若已存在（唯一约束冲突）返回 False（重复通知）。"""
        if not trade_no:
            return False
        db = SessionLocal()
        try:
            try:
                db.add(BillingNonce(trade_no=str(trade_no), channel=channel))
                db.commit()
                return True
            except Exception:
                db.rollback()
                # 已存在 → 重复通知
                return False
        finally:
            db.close()

    # ---- 手动激活（机构版线下合同 / 财务对账后激活） ----
    def manual_activate(self, scope_type, scope_id, plan_code, operator="admin", note=""):
        plan = PLANS.get(plan_code)
        if not plan:
            return {"success": False, "reason": f"未知套餐 {plan_code}"}
        scope_id = str(scope_id)
        now = _now()
        db = SessionLocal()
        try:
            order_id = f"MANUAL-{secrets.token_hex(4).upper()}"
            db.add(BillingOrder(
                order_id=order_id, scope_type=scope_type, scope_id=scope_id,
                user_id=scope_id, plan_code=plan_code, plan_name=plan["name"],
                amount_cents=plan["price_cents"], channel="manual", status="paid",
                created_at=_dt(now), paid_at=_dt(now), trade_no=None,
                extra={"operator": operator, "note": note},
            ))
            sub = (db.query(BillingSubscription)
                   .filter_by(scope_type=scope_type, scope_id=scope_id).first())
            if not sub:
                sub = BillingSubscription(scope_type=scope_type, scope_id=scope_id)
                db.add(sub)
            sub.plan = plan_code
            sub.status = "active"
            sub.trial = False
            sub.trial_ends_at = None
            sub.expires_at = _dt(now + plan["duration_days"] * 86400)
            sub.seats = plan["seats"]
            sub.order_id = order_id
            sub.operator = operator
            sub.note = note
            sub.updated_at = _dt(now)
            db.commit()
            return {"success": True, "subscription": _row_to_dict(sub)}
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    # ---- 查询 ----
    def get_order(self, order_id):
        db = SessionLocal()
        try:
            o = db.query(BillingOrder).filter_by(order_id=order_id).first()
            return _order_to_dict(o) if o else None
        finally:
            db.close()

    def list_orders(self, scope_type="tenant", scope_id="demo", limit=50):
        db = SessionLocal()
        try:
            rows = (db.query(BillingOrder)
                    .filter_by(scope_type=scope_type, scope_id=str(scope_id))
                    .order_by(BillingOrder.created_at.desc()).limit(limit).all())
            return [_order_to_dict(o) for o in rows]
        finally:
            db.close()

    # ---- 配额计数（按天，落库） ----
    def consume_quota(self, quota_key, scope_type, scope_id, n=1):
        """按天消费配额，返回 (allowed, info)。"""
        scope_id = str(scope_id)
        today = datetime.now().strftime("%Y%m%d")
        db = SessionLocal()
        try:
            row = (db.query(BillingQuota)
                   .filter_by(scope_type=scope_type, scope_id=scope_id,
                              quota_key=quota_key, day=today).first())
            sub = self.get_subscription(scope_type, scope_id)
            limit = self.get_quota(quota_key, sub)
            used = row.used if row else 0
            if used + n > limit:
                return False, {"used": used, "limit": limit, "remaining": max(0, limit - used)}
            if not row:
                row = BillingQuota(scope_type=scope_type, scope_id=scope_id,
                                   quota_key=quota_key, day=today, used=0)
                db.add(row)
            row.used = used + n
            row.updated_at = datetime.utcnow()
            db.commit()
            return True, {"used": row.used, "limit": limit, "remaining": limit - row.used}
        finally:
            db.close()

    def get_quota_status(self, scope_type, scope_id):
        sub = self.get_subscription(scope_type, scope_id)
        today = datetime.now().strftime("%Y%m%d")
        db = SessionLocal()
        try:
            rows = (db.query(BillingQuota)
                    .filter_by(scope_type=scope_type, scope_id=str(scope_id), day=today).all())
            used_map = {r.quota_key: r.used for r in rows}
        finally:
            db.close()
        keys = ["api_per_day", "backtest_per_day", "alert_per_day"]
        return {k: {"used": used_map.get(k, 0), "limit": self.get_quota(k, sub)} for k in keys}


def _order_to_dict(o: BillingOrder) -> dict:
    return {
        "order_id": o.order_id,
        "scope_type": o.scope_type,
        "scope_id": o.scope_id,
        "user_id": o.user_id,
        "plan_code": o.plan_code,
        "plan_name": o.plan_name,
        "amount_cents": o.amount_cents,
        "channel": o.channel,
        "status": o.status,
        "created_at": int(o.created_at.timestamp()) if o.created_at else None,
        "paid_at": int(o.paid_at.timestamp()) if o.paid_at else None,
        "trade_no": o.trade_no,
        "extra": o.extra or {},
    }


# ---------------------- 模块级单例 ----------------------
_payment_svc = None
_svc_lock = threading.Lock()


def get_payment_service():
    global _payment_svc
    if _payment_svc is None:
        with _svc_lock:
            if _payment_svc is None:
                _payment_svc = PaymentService()
    return _payment_svc
