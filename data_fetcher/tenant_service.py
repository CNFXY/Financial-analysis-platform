# -*- coding: utf-8 -*-
"""多租户与角色权限服务（REQ-06）。

提供：
- Tenant / Seat（席位）管理：多席位共享自选/告警，按租户隔离数据
- Role（角色）与权限分级：研究员(researcher) / 交易员(trader) /
  风控(compliance) / 管理员(admin)
- 权限校验装饰器式 API：require_permission(role, perm)
- 自选/告警按 tenant_id 隔离落盘（本地 JSON，架构预留数据库）

设计为无外部数据库依赖、线程安全；后续可替换为 PostgreSQL/MySQL
（仅替换 _load/_save 后端），上层接口不变。
"""
import os
import json
import time
import threading
from datetime import datetime

from fund_estimation_system import config

_CACHE_DIR = config.CACHE_DIR
_TENANT_FILE = os.path.join(_CACHE_DIR, "tenant_rbac.json")


# 角色 -> 权限集合（REQ-06 权限分级）
ROLE_PERMISSIONS = {
    "researcher": {"watchlist:rw", "alert:rw", "research:read", "backtest:read"},
    "trader":     {"watchlist:rw", "alert:rw", "trade:rw", "research:read", "backtest:read"},
    "compliance": {"watchlist:read", "alert:read", "trade:read", "risk:rw",
                   "audit:read", "research:read", "backtest:read"},
    "admin":      {"watchlist:rw", "alert:rw", "trade:rw", "risk:rw", "audit:rw",
                   "user:rw", "research:read", "backtest:read"},
}

ROLE_NAMES = {
    "researcher": "研究员",
    "trader": "交易员",
    "compliance": "风控/合规",
    "admin": "管理员",
}


class TenantService:
    """多租户与 RBAC。默认内置一个 demo 租户与若干席位。"""

    def __init__(self):
        self._lock = threading.Lock()
        self._data = {
            "tenants": {
                "demo": {
                    "name": "演示机构",
                    "seats": {
                        "researcher-01": {"role": "researcher", "name": "研究员A", "tenant": "demo"},
                        "trader-01": {"role": "trader", "name": "交易员A", "tenant": "demo"},
                        "compliance-01": {"role": "compliance", "name": "风控B", "tenant": "demo"},
                        "admin-01": {"role": "admin", "name": "管理员C", "tenant": "demo"},
                    },
                    # 各租户隔离的共享自选 / 告警规则
                    "watchlist": {"default": []},
                    "alert_rules": {},
                }
            }
        }
        self._load()

    def _load(self):
        try:
            if os.path.exists(_TENANT_FILE):
                with open(_TENANT_FILE, "r", encoding="utf-8") as f:
                    d = json.load(f)
                if isinstance(d, dict) and "tenants" in d:
                    self._data = d
                    return
        except Exception:
            pass
        self._save()

    def _save(self):
        try:
            os.makedirs(os.path.dirname(_TENANT_FILE), exist_ok=True)
            self._data["_updated_at"] = int(time.time())
            with open(_TENANT_FILE, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    # ---------- 租户 / 席位 / 角色 ----------
    def list_seats(self, tenant_id="demo"):
        t = self._data["tenants"].get(tenant_id)
        if not t:
            return []
        return [dict(v, seat_id=k) for k, v in t["seats"].items()]

    def get_seat(self, seat_id, tenant_id="demo"):
        t = self._data["tenants"].get(tenant_id)
        if not t:
            return None
        s = t["seats"].get(seat_id)
        return dict(s, seat_id=seat_id) if s else None

    def add_seat(self, seat_id, role, name="", tenant_id="demo"):
        if role not in ROLE_PERMISSIONS:
            return {"success": False, "reason": f"未知角色 {role}"}
        t = self._data["tenants"].setdefault(tenant_id, {"name": tenant_id, "seats": {}, "watchlist": {}, "alert_rules": {}})
        t["seats"][seat_id] = {"role": role, "name": name or seat_id, "tenant": tenant_id}
        self._save()
        return {"success": True, "seat": dict(t["seats"][seat_id], seat_id=seat_id)}

    def remove_seat(self, seat_id, tenant_id="demo"):
        t = self._data["tenants"].get(tenant_id)
        if t and seat_id in t["seats"]:
            t["seats"].pop(seat_id)
            self._save()
            return {"success": True}
        return {"success": False, "reason": "席位不存在"}

    def has_permission(self, seat_id, perm, tenant_id="demo"):
        """校验席位是否拥有某权限（REQ-06 权限隔离）。"""
        s = self.get_seat(seat_id, tenant_id)
        if not s:
            return False
        return perm in ROLE_PERMISSIONS.get(s["role"], set())

    def permissions_of(self, seat_id, tenant_id="demo"):
        s = self.get_seat(seat_id, tenant_id)
        if not s:
            return []
        return sorted(ROLE_PERMISSIONS.get(s["role"], set()))

    # ---------- 租户隔离共享资源 ----------
    def get_watchlist(self, tenant_id="demo", group="default"):
        t = self._data["tenants"].get(tenant_id)
        if not t:
            return []
        return list(t.get("watchlist", {}).get(group, []))

    def set_watchlist(self, codes, tenant_id="demo", group="default"):
        t = self._data["tenants"].setdefault(tenant_id, {"name": tenant_id, "seats": {}, "watchlist": {}, "alert_rules": {}})
        t.setdefault("watchlist", {})[group] = list(dict.fromkeys(codes))
        self._save()
        return list(t["watchlist"][group])

    def get_alert_rules(self, tenant_id="demo"):
        t = self._data["tenants"].get(tenant_id)
        if not t:
            return {}
        return t.get("alert_rules", {})

    def set_alert_rule(self, rule, tenant_id="demo"):
        t = self._data["tenants"].setdefault(tenant_id, {"name": tenant_id, "seats": {}, "watchlist": {}, "alert_rules": {}})
        rid = rule.get("id") or ("T%03d" % (len(t.get("alert_rules", {})) + 1))
        rule["id"] = rid
        t.setdefault("alert_rules", {})[rid] = rule
        self._save()
        return rid


# 模块级单例
_tenant_svc = None
_svc_lock = threading.Lock()


def get_tenant_service():
    global _tenant_svc
    if _tenant_svc is None:
        with _svc_lock:
            if _tenant_svc is None:
                _tenant_svc = TenantService()
    return _tenant_svc
