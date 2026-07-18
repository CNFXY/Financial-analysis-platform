# -*- coding: utf-8 -*-
"""实时行情增强服务（REQ-06/07/12 解耦模块）

提供：
- AlertEngine：价格突破/涨跌幅/成交量突增/盘口扫单 异动告警规则引擎（REQ-07）
- WatchlistStore：自选云端同步（基于本地 JSON 文件，多端共享，替代 localStorage，REQ-06）
- AuditLogger：操作审计留痕（REQ-12 留接口，满足合规审查前置）

设计为无外部依赖、线程安全，可直接被 web_server 调用。
"""
import os
import json
import time
import threading
from datetime import datetime

from fund_estimation_system import config

_CACHE_DIR = config.CACHE_DIR
_WATCHLIST_FILE = os.path.join(_CACHE_DIR, "realtime_watchlist.json")
_AUDIT_FILE = os.path.join(_CACHE_DIR, "realtime_audit.log")
_AUDIT_JSONL = os.path.join(_CACHE_DIR, "realtime_audit.jsonl")   # 结构化审计（P0-4 落库）
_ALERT_FILE = os.path.join(_CACHE_DIR, "realtime_alert_rules.json")
_RISK_FILE = os.path.join(_CACHE_DIR, "realtime_risk_config.json")     # 风控配置（P0-4）
_TRADE_FILE = os.path.join(_CACHE_DIR, "realtime_paper_account.json")  # 模拟盘账户（P0-3）


# ===================== 告警引擎（REQ-07） =====================
class AlertEngine:
    """异动告警规则引擎。

    支持四类规则（REQ-07）：
      - price_break: 价格突破指定阈值（上破/下破）
      - pct_change: 涨跌幅达到 N%
      - volume_surge: 成交量较基准突增 K 倍
      - sweep: 盘口扫单（买一/卖一大单，近似通过单笔量相对均值判断）

    规则与边沿状态持久化到本地 JSON 文件（与 WatchlistStore 一致），
    进程重启不丢失；边沿状态（_last_eval）同步落盘，避免重启后重复告警。
    """

    RULE_TYPES = ("price_break", "pct_change", "volume_surge", "sweep")

    def __init__(self):
        self._lock = threading.Lock()
        self._rules = {}          # rule_id -> rule dict
        self._rule_seq = 0
        self._last_eval = {}      # code -> {rule_id: bool} 边沿状态
        self._load()

    def _load(self):
        try:
            if os.path.exists(_ALERT_FILE):
                with open(_ALERT_FILE, "r", encoding="utf-8") as f:
                    d = json.load(f)
                if isinstance(d, dict):
                    self._rules = {k: dict(v) for k, v in d.get("rules", {}).items()}
                    self._rule_seq = d.get("seq", len(self._rules))
                    self._last_eval = d.get("last_eval", {})
                    return
        except Exception:
            pass
        self._save()

    def _save(self):
        """落盘（调用方须已持有 self._lock；threading.Lock 不可重入，故此处不再加锁）。"""
        try:
            os.makedirs(os.path.dirname(_ALERT_FILE), exist_ok=True)
            payload = {
                "rules": self._rules,
                "seq": self._rule_seq,
                "last_eval": self._last_eval,
            }
            with open(_ALERT_FILE, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def add_rule(self, rule):
        """新增/更新一条告警规则。

        rule: {type, code, params:{...}, enabled:true, name:''}
        返回 rule_id
        """
        with self._lock:
            rid = rule.get("id") or ("R%03d" % (self._rule_seq + 1))
            if not rule.get("id"):
                self._rule_seq += 1
            rule["id"] = rid
            rule.setdefault("enabled", True)
            rule.setdefault("name", self._default_name(rule))
            self._rules[rid] = rule
            self._save()
            return rid

    def remove_rule(self, rid):
        with self._lock:
            ok = self._rules.pop(rid, None) is not None
            if ok:
                # 同步清理该规则在所有标的上的边沿状态
                for code in self._last_eval:
                    self._last_eval[code].pop(rid, None)
                self._save()
            return ok

    def list_rules(self):
        with self._lock:
            return [dict(r) for r in self._rules.values()]

    def _default_name(self, rule):
        t = rule.get("type")
        code = rule.get("code", "")
        p = rule.get("params", {})
        if t == "price_break":
            return f"{code} 价格突破 {p.get('threshold')}"
        if t == "pct_change":
            return f"{code} 涨跌幅达 {p.get('pct')}%"
        if t == "volume_surge":
            return f"{code} 成交量突增 {p.get('multiple')}x"
        if t == "sweep":
            return f"{code} 盘口扫单(>{p.get('lots')}手)"
        return f"{code} 异动"

    def evaluate(self, quote):
        """评估单只行情是否触发告警。

        quote: 标准化行情 dict（与 TdxRealtimeClient 输出一致）
        返回: list[alert_dict] 本次新触发的告警（边沿触发，同一状态不重复报）
        """
        code = quote.get("code")
        if not code:
            return []
        alerts = []
        with self._lock:
            rules = list(self._rules.values())
        prev = self._last_eval.get(code, {})
        for r in rules:
            if not r.get("enabled"):
                continue
            if r.get("code") and r["code"] != code:
                continue
            triggered = self._match(r, quote)
            key = r["id"]
            if triggered and not prev.get(key):
                alerts.append({
                    "rule_id": key,
                    "rule_name": r.get("name", ""),
                    "code": code,
                    "name": quote.get("name", ""),
                    "type": r.get("type"),
                    "price": quote.get("price"),
                    "pct": (quote.get("price", 0) - quote.get("last_close", 0)),
                    "time": datetime.now().strftime("%H:%M:%S"),
                })
            # 记录本次边沿状态
            self._last_eval.setdefault(code, {})[key] = triggered
        # 边沿状态发生变更 -> 落盘（避免重启后重复告警）
        self._save()
        return alerts

    def _match(self, rule, q):
        t = rule.get("type")
        p = rule.get("params", {})
        try:
            if t == "price_break":
                thr = float(p.get("threshold", 0))
                price = float(q.get("price") or 0)
                # 突破方向由 direction 指定：up 上破 / down 下破 / both
                direction = p.get("direction", "both")
                if direction == "up":
                    return price >= thr
                if direction == "down":
                    return 0 < price <= thr
                return price >= thr or (0 < price <= thr)
            if t == "pct_change":
                last = float(q.get("last_close") or 0)
                price = float(q.get("price") or 0)
                if last <= 0:
                    return False
                pct = (price - last) / last * 100
                target = float(p.get("pct", 0))
                return abs(pct) >= abs(target)
            if t == "volume_surge":
                vol = int(q.get("volume") or 0)
                base = int(p.get("base_volume") or 0)
                mult = float(p.get("multiple", 3))
                if base <= 0:
                    return False
                return vol >= base * mult
            if t == "sweep":
                lots = int(p.get("lots") or 5000)
                # 盘口扫单近似：买一/卖一量超过阈值（大单）
                bids = q.get("bids") or []
                asks = q.get("asks") or []
                max_bid = max([b.get("vol", 0) for b in bids], default=0)
                max_ask = max([a.get("vol", 0) for a in asks], default=0)
                return max(max_bid, max_ask) >= lots
        except (TypeError, ValueError):
            return False
        return False


# ===================== 自选云端同步（REQ-06） =====================
class WatchlistStore:
    """自选列表云端同步（基于本地 JSON 文件，替代 localStorage）。

    支持多分组、团队共享（同文件即共享）、CSV 导入、批量增删。
    无外部数据库依赖，文件级读写保证刷新页面不丢失。
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._data = {"groups": {"default": []}, "updated_at": 0}
        self._load()

    def _load(self):
        try:
            if os.path.exists(_WATCHLIST_FILE):
                with open(_WATCHLIST_FILE, "r", encoding="utf-8") as f:
                    d = json.load(f)
                if isinstance(d, dict) and "groups" in d:
                    self._data = d
                    return
        except Exception:
            pass
        self._save()

    def _save(self):
        try:
            os.makedirs(os.path.dirname(_WATCHLIST_FILE), exist_ok=True)
            self._data["updated_at"] = int(time.time())
            with open(_WATCHLIST_FILE, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def get_all(self):
        with self._lock:
            return {g: list(codes) for g, codes in self._data["groups"].items()}

    def get_group(self, group="default"):
        with self._lock:
            return list(self._data["groups"].get(group, []))

    def add(self, code, group="default"):
        with self._lock:
            self._data["groups"].setdefault(group, [])
            if code not in self._data["groups"][group]:
                self._data["groups"][group].append(code)
            self._save()
        return True

    def remove(self, code, group="default"):
        with self._lock:
            g = self._data["groups"].get(group, [])
            if code in g:
                g.remove(code)
                self._save()
        return True

    def set_group(self, group, codes):
        with self._lock:
            self._data["groups"][group] = list(dict.fromkeys(codes))  # 去重保序
            self._save()
        return True

    def import_csv(self, text):
        """从 CSV 文本批量导入（每行: code[,name]）"""
        added = []
        with self._lock:
            self._data["groups"].setdefault("default", [])
            for line in text.splitlines():
                line = line.strip()
                if not line:
                    continue
                code = line.split(",")[0].strip()
                if code and code not in self._data["groups"]["default"]:
                    self._data["groups"]["default"].append(code)
                    added.append(code)
            self._save()
        return added


# ===================== 操作审计（REQ-12） =====================
class AuditLogger:
    """操作审计留痕（REQ-12 前置）。

    所有查询/下单/告警操作写入本地审计日志，满足合规审查。
    设计为可后续替换为合规审计中心（如 Kafka/数据库），当前落本地文件。
    """

    def __init__(self):
        self._lock = threading.Lock()

    def log(self, action, detail=None, operator="anonymous", level="INFO"):
        """记录一条审计事件（同时写人类可读日志与结构化 JSONL，P0-4 落库）。

        action: 操作类型（query/order/cancel/risk_block/alert/export...）
        detail: 详情 dict 或字符串
        """
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        detail_str = detail
        if isinstance(detail, dict):
            try:
                detail_str = json.dumps(detail, ensure_ascii=False)
            except Exception:
                detail_str = str(detail)
        line = f"{ts} [{level}] operator={operator} action={action} {detail_str or ''}\n"
        record = {
            "ts": ts, "level": level, "operator": operator,
            "action": action, "detail": detail,
        }
        with self._lock:
            try:
                with open(_AUDIT_FILE, "a", encoding="utf-8") as f:
                    f.write(line)
            except Exception:
                pass
            try:
                with open(_AUDIT_JSONL, "a", encoding="utf-8") as f:
                    f.write(json.dumps(record, ensure_ascii=False) + "\n")
            except Exception:
                pass

    def recent(self, limit=200):
        try:
            with open(_AUDIT_FILE, "r", encoding="utf-8") as f:
                lines = f.readlines()
            return lines[-limit:]
        except Exception:
            return []

    def query(self, action=None, operator=None, level=None, limit=500):
        """结构化检索审计事件（P0-4：可检索）。返回 list[dict]。"""
        out = []
        try:
            with open(_AUDIT_JSONL, "r", encoding="utf-8") as f:
                for ln in f:
                    ln = ln.strip()
                    if not ln:
                        continue
                    try:
                        r = json.loads(ln)
                    except Exception:
                        continue
                    if action and r.get("action") != action:
                        continue
                    if operator and r.get("operator") != operator:
                        continue
                    if level and r.get("level") != level:
                        continue
                    out.append(r)
        except Exception:
            return []
        return out[-limit:]

    def export_csv(self):
        """导出审计为 CSV 文本（P0-4：可导出）。"""
        rows = self.query(limit=100000)
        lines = ["ts,level,operator,action,detail"]
        for r in rows:
            d = r.get("detail")
            if isinstance(d, dict):
                d = json.dumps(d, ensure_ascii=False)
            d = str(d or "").replace('"', "'").replace("\n", " ")
            lines.append(f'{r.get("ts","")},{r.get("level","")},{r.get("operator","")},{r.get("action","")},"{d}"')
        return "\n".join(lines)


# ===================== 风控引擎（P0-4） =====================
class RiskEngine:
    """交易前风控校验引擎（P0-4 合规门槛）。

    校验维度：
      - 单笔金额上限（max_order_amount）
      - 单标的持仓市值占比上限（max_position_pct）
      - 总仓位上限（max_total_position_pct，占总资产比例）
      - 禁投池（blacklist：命中直接拒单）
    止损止盈（stop_loss_pct / take_profit_pct）由交易引擎持仓时监测。
    配置持久化到本地 JSON，重启不丢。
    """

    DEFAULT = {
        "max_order_amount": 500000.0,   # 单笔上限 50 万
        "max_position_pct": 30.0,       # 单标的市值占比上限 30%
        "max_total_position_pct": 95.0, # 总仓位上限 95%
        "stop_loss_pct": 8.0,           # 止损线 -8%
        "take_profit_pct": 20.0,        # 止盈线 +20%
        "blacklist": [],                # 禁投池
    }

    def __init__(self):
        self._lock = threading.Lock()
        self._cfg = dict(self.DEFAULT)
        self._load()

    def _load(self):
        try:
            if os.path.exists(_RISK_FILE):
                with open(_RISK_FILE, "r", encoding="utf-8") as f:
                    d = json.load(f)
                if isinstance(d, dict):
                    self._cfg.update(d)
                    return
        except Exception:
            pass
        self._save()

    def _save(self):
        try:
            os.makedirs(os.path.dirname(_RISK_FILE), exist_ok=True)
            with open(_RISK_FILE, "w", encoding="utf-8") as f:
                json.dump(self._cfg, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def get_config(self):
        with self._lock:
            return dict(self._cfg)

    def update_config(self, patch):
        with self._lock:
            for k, v in (patch or {}).items():
                if k in self.DEFAULT:
                    self._cfg[k] = v
            self._save()
            return dict(self._cfg)

    def check_order(self, code, side, price, qty, account_snapshot):
        """下单前风控校验。返回 (ok:bool, reasons:list[str])。

        account_snapshot: {total_asset, cash, positions:{code:{qty,market_value}}}
        """
        with self._lock:
            cfg = dict(self._cfg)
        reasons = []
        amount = float(price) * int(qty)
        total = max(1.0, float(account_snapshot.get("total_asset", 0)))
        # 1) 禁投池
        if code in (cfg.get("blacklist") or []):
            reasons.append(f"标的 {code} 在禁投池中，禁止交易")
        # 2) 单笔金额上限
        if amount > cfg["max_order_amount"]:
            reasons.append(f"单笔金额 {amount:.0f} 超过上限 {cfg['max_order_amount']:.0f}")
        if side == "buy":
            # 3) 单标的持仓占比上限（含本次）
            pos = account_snapshot.get("positions", {}).get(code, {})
            new_mv = float(pos.get("market_value", 0)) + amount
            if new_mv / total * 100 > cfg["max_position_pct"]:
                reasons.append(f"标的 {code} 持仓占比 {new_mv/total*100:.1f}% 超过上限 {cfg['max_position_pct']}%")
            # 4) 总仓位上限
            cur_pos_mv = sum(float(p.get("market_value", 0)) for p in account_snapshot.get("positions", {}).values())
            new_total_pct = (cur_pos_mv + amount) / total * 100
            if new_total_pct > cfg["max_total_position_pct"]:
                reasons.append(f"总仓位 {new_total_pct:.1f}% 超过上限 {cfg['max_total_position_pct']}%")
            # 5) 现金充足
            if amount > float(account_snapshot.get("cash", 0)):
                reasons.append(f"可用现金不足（需 {amount:.0f}，可用 {account_snapshot.get('cash',0):.0f}）")
        return (len(reasons) == 0), reasons


# ===================== 模拟盘交易引擎（P0-3） =====================
class PaperTradingEngine:
    """模拟盘交易引擎（P0-3，交易通道-模拟盘优先）。

    - 下单/撤单/持仓/订单查询；市价即时成交（以传入 price 撮合）
    - 下单前强制经 RiskEngine 校验；违规拦截并审计留痕
    - 账户与订单持久化，重启不丢
    架构预留：实盘网关仅需替换 _fill() 为券商 API 调用。
    """

    INIT_CASH = 1000000.0  # 初始模拟资金 100 万

    def __init__(self, risk_engine=None, audit_logger=None):
        self._lock = threading.Lock()
        self.risk = risk_engine or get_risk_engine()
        self.audit = audit_logger or get_audit_logger()
        self._acc = {
            "cash": self.INIT_CASH,
            "positions": {},   # code -> {qty, cost, market_value, last_price, name}
            "orders": [],      # 订单流水
            "order_seq": 0,
        }
        self._load()

    def _load(self):
        try:
            if os.path.exists(_TRADE_FILE):
                with open(_TRADE_FILE, "r", encoding="utf-8") as f:
                    d = json.load(f)
                if isinstance(d, dict) and "cash" in d:
                    self._acc = d
                    return
        except Exception:
            pass
        self._save()

    def _save(self):
        try:
            os.makedirs(os.path.dirname(_TRADE_FILE), exist_ok=True)
            with open(_TRADE_FILE, "w", encoding="utf-8") as f:
                json.dump(self._acc, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _snapshot(self):
        pos_mv = sum(float(p.get("market_value", 0)) for p in self._acc["positions"].values())
        return {
            "total_asset": self._acc["cash"] + pos_mv,
            "cash": self._acc["cash"],
            "positions": self._acc["positions"],
        }

    def account(self, price_map=None):
        """返回账户快照。price_map: {code:last_price} 用于刷新持仓市值。"""
        with self._lock:
            if price_map:
                for code, p in self._acc["positions"].items():
                    lp = price_map.get(code)
                    if lp:
                        p["last_price"] = lp
                        p["market_value"] = round(lp * p["qty"], 2)
                        p["pnl"] = round((lp - p["cost"]) * p["qty"], 2)
                        p["pnl_pct"] = round((lp - p["cost"]) / p["cost"] * 100, 2) if p["cost"] else 0
                self._save()
            pos_mv = sum(float(p.get("market_value", 0)) for p in self._acc["positions"].values())
            return {
                "cash": round(self._acc["cash"], 2),
                "position_value": round(pos_mv, 2),
                "total_asset": round(self._acc["cash"] + pos_mv, 2),
                "positions": self._acc["positions"],
                "orders": self._acc["orders"][-50:],
            }

    def place_order(self, code, side, price, qty, name="", operator="paper_trader"):
        """下单（市价即时撮合）。返回 dict：{success, order_id?, reasons?}。"""
        side = (side or "").lower()
        price = float(price or 0)
        qty = int(qty or 0)
        if side not in ("buy", "sell") or price <= 0 or qty <= 0:
            return {"success": False, "reasons": ["参数非法：side/price/qty"]}
        with self._lock:
            # 卖出需持仓充足
            if side == "sell":
                pos = self._acc["positions"].get(code)
                if not pos or pos["qty"] < qty:
                    self.audit.log("risk_block", {"code": code, "side": side, "reason": "持仓不足"}, operator, level="WARN")
                    return {"success": False, "reasons": ["持仓不足，无法卖出"]}
            # 风控校验（买入）
            ok, reasons = self.risk.check_order(code, side, price, qty, self._snapshot())
            if not ok:
                self.audit.log("risk_block", {"code": code, "side": side, "price": price, "qty": qty, "reasons": reasons}, operator, level="WARN")
                return {"success": False, "reasons": reasons}
            # 撮合成交
            oid = "O%06d" % (self._acc["order_seq"] + 1)
            self._acc["order_seq"] += 1
            amount = price * qty
            if side == "buy":
                self._acc["cash"] -= amount
                pos = self._acc["positions"].get(code, {"qty": 0, "cost": 0.0, "name": name})
                new_qty = pos["qty"] + qty
                pos["cost"] = round((pos["cost"] * pos["qty"] + amount) / new_qty, 4) if new_qty else 0
                pos["qty"] = new_qty
                pos["name"] = name or pos.get("name", "")
                pos["last_price"] = price
                pos["market_value"] = round(price * new_qty, 2)
                self._acc["positions"][code] = pos
            else:
                self._acc["cash"] += amount
                pos = self._acc["positions"][code]
                pos["qty"] -= qty
                if pos["qty"] <= 0:
                    self._acc["positions"].pop(code, None)
                else:
                    pos["market_value"] = round(price * pos["qty"], 2)
            order = {
                "id": oid, "code": code, "name": name, "side": side,
                "price": price, "qty": qty, "amount": round(amount, 2),
                "status": "filled",
                "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
            self._acc["orders"].append(order)
            self._save()
            self.audit.log("order", order, operator, level="INFO")
            return {"success": True, "order_id": oid, "order": order}

    def cancel_order(self, order_id, operator="paper_trader"):
        """撤单（模拟盘为即时成交，仅支持撤未成交单；此处演示接口完整性）。"""
        with self._lock:
            for o in self._acc["orders"]:
                if o["id"] == order_id and o["status"] == "pending":
                    o["status"] = "cancelled"
                    self._save()
                    self.audit.log("cancel", {"order_id": order_id}, operator)
                    return {"success": True}
            return {"success": False, "reasons": ["订单不存在或已成交，无法撤销"]}

    def check_stop(self, price_map):
        """止损止盈监测（P0-4）：返回需强平的持仓列表（不自动执行，交由前端确认）。"""
        cfg = self.risk.get_config()
        sl = -abs(cfg.get("stop_loss_pct", 8))
        tp = abs(cfg.get("take_profit_pct", 20))
        hits = []
        with self._lock:
            for code, p in self._acc["positions"].items():
                lp = price_map.get(code) or p.get("last_price")
                if not lp or not p.get("cost"):
                    continue
                pct = (lp - p["cost"]) / p["cost"] * 100
                if pct <= sl:
                    hits.append({"code": code, "name": p.get("name", ""), "pnl_pct": round(pct, 2), "type": "stop_loss"})
                elif pct >= tp:
                    hits.append({"code": code, "name": p.get("name", ""), "pnl_pct": round(pct, 2), "type": "take_profit"})
        return hits


# 模块级单例
_alert_engine = None
_watchlist_store = None
_audit_logger = None
_risk_engine = None
_paper_engine = None
_singleton_lock = threading.Lock()


def get_alert_engine():
    global _alert_engine
    if _alert_engine is None:
        with _singleton_lock:
            if _alert_engine is None:
                _alert_engine = AlertEngine()
    return _alert_engine


def get_watchlist_store():
    global _watchlist_store
    if _watchlist_store is None:
        with _singleton_lock:
            if _watchlist_store is None:
                _watchlist_store = WatchlistStore()
    return _watchlist_store


def get_audit_logger():
    global _audit_logger
    if _audit_logger is None:
        with _singleton_lock:
            if _audit_logger is None:
                _audit_logger = AuditLogger()
    return _audit_logger


def get_risk_engine():
    global _risk_engine
    if _risk_engine is None:
        with _singleton_lock:
            if _risk_engine is None:
                _risk_engine = RiskEngine()
    return _risk_engine


def get_paper_engine():
    global _paper_engine
    if _paper_engine is None:
        with _singleton_lock:
            if _paper_engine is None:
                _paper_engine = PaperTradingEngine()
    return _paper_engine
