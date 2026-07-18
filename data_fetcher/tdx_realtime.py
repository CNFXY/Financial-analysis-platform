# -*- coding: utf-8 -*-
"""通达信实时行情客户端（基于 pytdx 直连行情服务器）

提供:
- 实时快照行情 (get_security_quotes): 最新价、涨跌、涨跌幅、开高低、五档盘口
- 分时数据 (get_minute_time_data)
- 历史 K 线 (get_security_bars)
- 自选股批量实时报价
- 服务器自动优选 + 短缓存，降低请求频率

注意:
- 通达信行情服务器为公开行情站，仅交易时段（含集合竞价）返回有效 price。
- 非交易时段 price 可能为 0，此时以 last_close 作为参考价，页面据此提示。
"""
import os
import json
import time
import threading
from datetime import datetime, date

try:
    from pytdx.hq import TdxHq_API
    from pytdx.params import TDXParams
    PYTDX_AVAILABLE = True
except ImportError:
    PYTDX_AVAILABLE = False
    TdxHq_API = None
    TDXParams = None

from fund_estimation_system import config


# 常用通达信行情服务器（公开行情站，端口 7709）
DEFAULT_SERVERS = [
    ("115.238.56.198", 7709),
    ("218.108.98.244", 7709),
    ("114.80.63.12", 7709),
    ("119.147.212.81", 7709),
    ("123.125.108.23", 7709),
    ("47.92.127.181", 7709),
    ("8.133.240.123", 7709),
    ("47.107.75.242", 7709),
    ("112.74.214.154", 7709),
]

# 行情缓存时长（秒）：实时报价缓存 1.5s，避免过于频繁请求服务器
REALTIME_CACHE_TTL = 1.5
KLINE_CACHE_TTL = 30

# 行情陈旧阈值（秒）：超过该时长未拿到有效更新视为 stale（REQ-03 断连/陈旧告警）
STALE_THRESHOLD = 5


class QuoteProvider:
    """行情数据源抽象接口（REQ-01 前置）。

    所有行情源（pytdx 公开站、授权 L1/L2、商业数据商）均应实现本接口，
    便于在合规授权源就绪后做无缝替换，pytdx 仅作为降级兜底。
    """

    name = "base"

    def status(self):
        raise NotImplementedError

    def get_realtime_quotes(self, codes):
        raise NotImplementedError

    def get_single_quote(self, code):
        raise NotImplementedError

    def get_minute_data(self, code):
        raise NotImplementedError

    def get_kline(self, code, ktype="day", count=120):
        raise NotImplementedError

    def search(self, query, limit=20):
        raise NotImplementedError


def _code_to_market(code):
    """代码 -> (market, pure_code)

    支持:
    - 带前缀: sh600519 / SH600519 / 600519.SH
    - 纯数字: 60xxxx/68xxxx/51xxxx -> 上海; 00xxxx/30xxxx/15xxxx/39xxxx -> 深圳
    """
    c = str(code).strip().upper()
    c = c.replace(".SH", "").replace(".SZ", "").replace(".BJ", "")
    if c.startswith("SH"):
        return TDXParams.MARKET_SH, c[2:]
    if c.startswith("SZ"):
        return TDXParams.MARKET_SZ, c[2:]
    if c.startswith("BJ"):
        return TDXParams.MARKET_SH, c[2:]  # pytdx 无 BJ 常量，北京用 SH 近似
    if c.startswith(("60", "68", "51", "90", "88", "99", "11", "50", "55", "58")):
        return TDXParams.MARKET_SH, c
    if c.startswith(("00", "30", "15", "39", "20", "12", "16", "18")):
        return TDXParams.MARKET_SZ, c
    # 默认上海
    return TDXParams.MARKET_SH, c


def _is_valid_code(code):
    """判断是否为合法的证券代码（6位数字，可带 sh/sz/bj 前缀或 .SH/.SZ 后缀）"""
    if not code:
        return False
    c = str(code).strip().upper()
    c = c.replace(".SH", "").replace(".SZ", "").replace(".BJ", "")
    for pre in ("SH", "SZ", "BJ"):
        if c.startswith(pre):
            c = c[len(pre):]
            break
    return c.isdigit() and len(c) == 6


# 指数代码段（无五档盘口，需走专用逻辑，不可按个股解析）
_INDEX_PREFIXES = ("999", "399", "000300", "000688", "000905", "000016",
                  "000001", "399001", "399006", "399005")


def _is_index_code(code):
    """判断是否为指数代码（如 999999 上证指数、399001 深证成指、399006 创业板指等）

    注意：000001 在深圳为「平安银行」、在上海为「上证指数」，pytdx 按市场区分；
    此处仅将无歧义的指数段（999/399 开头及沪深300等专用码）判为指数，避免与
    个股（如 000001 平安银行）冲突。
    """
    c = str(code).strip().upper()
    c = c.replace(".SH", "").replace(".SZ", "").replace(".BJ", "")
    c = c.replace("SH", "").replace("SZ", "").replace("BJ", "")
    if not c.isdigit():
        return False
    if c in ("000300", "000688", "000905", "000016", "399001", "399006", "399005", "399300"):
        return True
    return c.startswith(("999", "399"))


class TdxRealtimeClient(QuoteProvider):
    """通达信实时行情客户端（线程安全，带连接池与缓存）

    作为 QuoteProvider 的默认实现（兜底数据源）。生产环境下可叠加
    AuthQuoteProvider（授权 L1/L2）作为主源，本类保留为降级 fallback。
    """

    name = "pytdx"

    def __init__(self, servers=None):
        self.available = PYTDX_AVAILABLE
        self.servers = servers or DEFAULT_SERVERS
        self._best_server = None
        self._lock = threading.Lock()
        self._api = None
        self._connected_at = 0
        # REQ-03: 连接健康与陈旧检测
        self._last_success_at = 0      # 最近一次成功获取到有效行情的时间戳
        self._last_error = ""          # 最近一次错误描述
        self._reconnect_count = 0      # 累计重连次数（自愈计数）
        # 缓存: key -> (timestamp, data)
        self._cache = {}
        self._cache_ttl = {}
        self._market_name = {0: "深圳", 1: "上海"}
        # 证券名称索引: code -> {"name":..., "market":0/1}
        self._name_idx = {}
        self._name_idx_loaded = False
        self._name_idx_lock = threading.Lock()
        self._name_idx_file = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "cache", "tdx_security_names.json"
        )

    # ---------- 连接管理 ----------
    def _ensure_connection(self):
        """确保已连接最优服务器；失败自动切换；死连接主动重连"""
        if not self.available:
            return False
        now = time.time()
        # 已有连接：60s 内且探活通过则复用
        if self._api is not None and (now - self._connected_at) < 60:
            if self._alive():
                return True
            # 连接已死，断开重连
            try:
                self._api.disconnect()
            except Exception:
                pass
            self._api = None
        # 关闭旧连接
        try:
            if self._api is not None:
                self._api.disconnect()
        except Exception:
            pass
        self._api = None

        servers = [self._best_server] + self.servers if self._best_server else self.servers
        for host, port in servers:
            try:
                api = TdxHq_API(raise_exception=False, auto_retry=True)
                if api.connect(host, port, time_out=4):
                    self._api = api
                    self._best_server = (host, port)
                    self._connected_at = now
                    self._reconnect_count += 1
                    return True
            except Exception:
                continue
        return False

    def disconnect(self):
        try:
            if self._api is not None:
                self._api.disconnect()
        except Exception:
            pass
        self._api = None

    def _alive(self):
        """轻量探测连接是否仍然有效（避免死连接静默返回空）"""
        if self._api is None:
            return False
        try:
            # get_security_count 是极轻量的接口，用于探活
            cnt = self._api.get_security_count(0)
            return cnt is not None and cnt > 0
        except Exception:
            return False

    # ---------- 证券名称索引 ----------
    def _ensure_name_index(self, force=False):
        """确保证券名称索引已加载。

        优先读本地缓存文件（当日有效）；否则从行情服务器分页全量拉取并落盘。
        """
        if self._name_idx_loaded and not force:
            return
        with self._name_idx_lock:
            if self._name_idx_loaded and not force:
                return
            # 1) 尝试读本地缓存（当日有效）
            if not force and self._load_name_index_from_file():
                self._name_idx_loaded = True
                return
            # 2) 从行情服务器全量拉取
            if self._build_name_index_from_server():
                self._name_idx_loaded = True
                self._save_name_index_to_file()

    def _load_name_index_from_file(self):
        try:
            if not os.path.exists(self._name_idx_file):
                return False
            # 缓存当日有效（避免跨日名称变动/新股遗漏）
            mtime = date.fromtimestamp(os.path.getmtime(self._name_idx_file))
            if mtime != date.today():
                return False
            with open(self._name_idx_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and data:
                self._name_idx = data
                return True
        except Exception:
            pass
        return False

    def _save_name_index_to_file(self):
        try:
            os.makedirs(os.path.dirname(self._name_idx_file), exist_ok=True)
            with open(self._name_idx_file, "w", encoding="utf-8") as f:
                json.dump(self._name_idx, f, ensure_ascii=False)
        except Exception:
            pass

    def _build_name_index_from_server(self):
        """分页拉取沪深全市场证券列表（含名称），构建代码->{name,market} 索引"""
        if not self._ensure_connection():
            return False
        idx = {}
        try:
            for market in (1, 0):  # 1=上海 0=深圳
                try:
                    total = self._api.get_security_count(market)
                except Exception:
                    total = 0
                if not total:
                    continue
                for start in range(0, total, 1000):
                    try:
                        lst = self._api.get_security_list(market, start)
                    except Exception:
                        lst = None
                    if not lst:
                        continue
                    for it in lst:
                        code = it.get("code")
                        name = (it.get("name") or "").strip()
                        if code and name:
                            idx[code] = {"name": name, "market": market}
        except Exception as e:
            print(f"[WARN] 构建证券名称索引失败: {e}")
        if idx:
            self._name_idx = idx
            return True
        return False

    def get_name(self, code):
        """按代码获取证券名称（真实，来自行情服务器证券列表）"""
        self._ensure_name_index()
        c = str(code).upper().replace(".SH", "").replace(".SZ", "").replace(".BJ", "")
        c = c.replace("SH", "").replace("SZ", "").replace("BJ", "")
        info = self._name_idx.get(c)
        return info["name"] if info else ""

    # ---------- 缓存 ----------
    def _get_cache(self, key, ttl):
        item = self._cache.get(key)
        ts = item[0] if item else None
        if item and (time.time() - ts) < ttl:
            return item[1]
        return None

    def _set_cache(self, key, data, ttl):
        self._cache[key] = (time.time(), data)
        self._cache_ttl[key] = ttl

    # ---------- 行情接口 ----------
    def get_realtime_quotes(self, codes):
        """批量获取实时行情快照

        Args:
            codes: list[str] 股票/基金代码列表
        Returns:
            list[dict]: 标准化行情
        """
        # 过滤非法代码（如误存入的中文名称），避免坏代码拖垮整批请求
        valid_codes = [c for c in codes if _is_valid_code(c)]
        if not valid_codes:
            return []
        # 去重（DEF-04）：同一代码无论是否带前缀都只请求一次，并归一化为纯代码
        seen, norm_codes = set(), []
        for c in valid_codes:
            _, pure = _code_to_market(c)
            if pure not in seen:
                seen.add(pure)
                norm_codes.append(pure)
        codes = norm_codes

        cache_key = "rt_" + "|".join(sorted(codes))
        cached = self._get_cache(cache_key, REALTIME_CACHE_TTL)
        if cached is not None:
            return cached

        if not self._ensure_connection():
            return []

        pairs = []
        idx_map = {}
        for i, c in enumerate(codes):
            m, pure = _code_to_market(c)
            pairs.append((m, pure))
            idx_map[(m, pure)] = pure  # DEF-03: 返回统一用纯代码

        try:
            raw = self._api.get_security_quotes(pairs)
        except Exception as e:
            self._last_error = f"get_security_quotes 失败: {e}"
            print(f"[ERROR] TDX实时行情失败: {e}")
            return []

        result = self._parse_quotes(raw, idx_map) if raw else []
        # 若预期应有数据却拿到空（开盘瞬间死连接/服务器空快照），强制重连重试一次
        if not result and codes:
            try:
                self.disconnect()
                self._api = None
                if self._ensure_connection():
                    raw2 = self._api.get_security_quotes(pairs)
                    if raw2:
                        result = self._parse_quotes(raw2, idx_map)
            except Exception:
                pass
        self._set_cache(cache_key, result, REALTIME_CACHE_TTL)
        if result:
            self._last_success_at = time.time()
            self._last_error = ""
        return result

    def _parse_quotes(self, raw, idx_map):
        """将原始行情解析为标准 dict 列表"""
        result = []
        if not raw:
            return result
        # 确保名称索引可用（快照接口不含名称，需从证券列表补全）
        self._ensure_name_index()
        for q in raw:
            mkt = q.get("market")
            pure = q.get("code")
            price = float(q.get("price") or 0)
            last_close = float(q.get("last_close") or 0)
            ref_price = price if price > 0 else last_close
            change = (ref_price - last_close) if last_close > 0 else 0
            change_pct = (change / last_close * 100) if last_close > 0 else 0
            name = (q.get("name") or "").strip()
            is_index = _is_index_code(pure)
            if not name:
                # 指数代码的名称在证券列表中常为空，按代码识别给出可读名称
                if is_index:
                    name = self._index_name(pure)
                else:
                    info = self._name_idx.get(pure)
                    name = info["name"] if info else self._known_name(pure)
                if not name:
                    name = pure  # 最终兜底，避免空名误导
            # 指数无五档盘口，原始 bid/ask 为垃圾值，统一清零（DEF-02）
            if is_index:
                for k in ("bid1", "ask1", "bid_vol1", "ask_vol1",
                          "bid2", "ask2", "bid_vol2", "ask_vol2",
                          "bid3", "ask3", "bid_vol3", "ask_vol3",
                          "bid4", "ask4", "bid_vol4", "ask_vol4",
                          "bid5", "ask5", "bid_vol5", "ask_vol5"):
                    q[k] = 0
            result.append({
                "code": idx_map.get((mkt, pure), pure),
                "pure_code": pure,
                "market": self._market_name.get(mkt, str(mkt)),
                "name": name,
                "price": round(ref_price, 3),
                "last_close": round(last_close, 3),
                "open": round(float(q.get("open") or 0), 3),
                "high": round(float(q.get("high") or 0), 3),
                "low": round(float(q.get("low") or 0), 3),
                "volume": int(q.get("vol") or 0),
                "amount": float(q.get("amount") or 0),
                "bid1": round(float(q.get("bid1") or 0), 3),
                "ask1": round(float(q.get("ask1") or 0), 3),
                "bid_vol1": int(q.get("bid_vol1") or 0),
                "ask_vol1": int(q.get("ask_vol1") or 0),
                "servertime": q.get("servertime", ""),
                "is_trading": price > 0,
            })
        return result

    def get_single_quote(self, code):
        """单只实时报价 + 五档盘口"""
        quotes = self.get_realtime_quotes([code])
        if not quotes:
            return None
        q = quotes[0]
        # 指数无五档盘口，按个股解析会得到垃圾盘口（DEF-02），直接跳过
        if _is_index_code(code):
            q["is_index"] = True
            return q
        # 拉取完整五档
        if not self._ensure_connection():
            return q
        m, pure = _code_to_market(code)
        try:
            raw = self._api.get_security_quotes([(m, pure)])
            if raw:
                r = raw[0]
                q["bids"] = [
                    {"price": round(float(r.get("bid1") or 0), 3), "vol": int(r.get("bid_vol1") or 0)},
                    {"price": round(float(r.get("bid2") or 0), 3), "vol": int(r.get("bid_vol2") or 0)},
                    {"price": round(float(r.get("bid3") or 0), 3), "vol": int(r.get("bid_vol3") or 0)},
                    {"price": round(float(r.get("bid4") or 0), 3), "vol": int(r.get("bid_vol4") or 0)},
                    {"price": round(float(r.get("bid5") or 0), 3), "vol": int(r.get("bid_vol5") or 0)},
                ]
                q["asks"] = [
                    {"price": round(float(r.get("ask1") or 0), 3), "vol": int(r.get("ask_vol1") or 0)},
                    {"price": round(float(r.get("ask2") or 0), 3), "vol": int(r.get("ask_vol2") or 0)},
                    {"price": round(float(r.get("ask3") or 0), 3), "vol": int(r.get("ask_vol3") or 0)},
                    {"price": round(float(r.get("ask4") or 0), 3), "vol": int(r.get("ask_vol4") or 0)},
                    {"price": round(float(r.get("ask5") or 0), 3), "vol": int(r.get("ask_vol5") or 0)},
                ]
        except Exception:
            pass
        return q

    def get_minute_data(self, code):
        """分时数据（当日）

        实现说明：pytdx 的 get_minute_time_data 在部分行情站/版本下返回的分时序列
        头部夹带索引残留（price=0.01/0.49/1.06 等）、且整体价格存在偏移，无法可靠
        还原真实分时价。因此改用 get_security_bars(1分钟) 构建分时序列——其 close 价
        与实时快照一致（已验证），且自带 datetime，数据准确可靠。

        返回: list[{"price": 分时收盘价, "vol": 该分钟成交量(手), "time": "HH:MM"}]
        """
        cache_key = "min_" + str(code)
        cached = self._get_cache(cache_key, REALTIME_CACHE_TTL)
        if cached is not None:
            return cached
        if not self._ensure_connection():
            return []
        m, pure = _code_to_market(code)
        data = []
        try:
            # 8 = 1分钟K线；取足够多的点数覆盖当日
            raw = self._api.get_security_bars(8, m, pure, 0, 240)
        except Exception:
            raw = None
        if raw:
            for bar in raw:
                try:
                    price = float(bar.get("close") or 0)
                    vol = int(bar.get("vol") or 0)
                except (TypeError, ValueError):
                    continue
                if price <= 0:
                    continue
                hh = bar.get("hour"); mm = bar.get("minute")
                t = f"{int(hh):02d}:{int(mm):02d}" if hh is not None else ""
                data.append({
                    "price": round(price, 3),
                    "vol": vol,
                    "time": t,
                })
        self._set_cache(cache_key, data, REALTIME_CACHE_TTL)
        return data

    def get_kline(self, code, ktype="day", count=120):
        """历史 K 线

        ktype: day / week / month / 1min / 5min
        """
        cache_key = f"kline_{code}_{ktype}_{count}"
        cached = self._get_cache(cache_key, KLINE_CACHE_TTL)
        if cached is not None:
            return cached
        if not self._ensure_connection():
            return []
        m, pure = _code_to_market(code)
        type_map = {
            "day": 9, "week": 5, "month": 6, "1min": 8, "5min": 0, "15min": 1, "30min": 2, "60min": 3,
        }
        ttype = type_map.get(ktype, 9)
        try:
            raw = self._api.get_security_bars(ttype, m, pure, 0, count)
        except Exception:
            raw = None
        data = []
        if raw:
            for bar in raw:
                data.append({
                    "date": str(bar.get("datetime") or bar.get("date") or ""),
                    "open": round(float(bar.get("open") or 0), 3),
                    "close": round(float(bar.get("close") or 0), 3),
                    "high": round(float(bar.get("high") or 0), 3),
                    "low": round(float(bar.get("low") or 0), 3),
                    "volume": int(bar.get("vol") or 0),
                    "amount": float(bar.get("amount") or 0),
                })
        self._set_cache(cache_key, data, KLINE_CACHE_TTL)
        return data

    def search(self, query, limit=20):
        """按代码或名称关键词搜索可交易标的（真实数据，直连行情服务器）

        覆盖范围:
        - 场内品种：股票、ETF、指数、可转债（来自 pytdx 行情站证券列表索引）；
        - 场外开放式基金（如 161725 招商中证白酒、110011 易方达消费行业等）：
          pytdx 行情站不含此类标的，故额外接入 Tushare 基金列表作为兜底数据源。

        策略:
        1. 若输入形如代码（数字/带前缀），先在全市场索引中精确/前缀匹配，再实时验证；
           场内查不到时回退到 Tushare 基金列表（含场外基金）。
        2. 若输入为名称片段，则在全市场索引 + Tushare 基金列表中做名称模糊匹配。

        Returns:
            list[dict]: {code, name, market, kind}
        """
        q = (query or "").strip()
        if not q:
            return []
        # 参数校验（DEF-05）：限制查询长度，防止异常输入拖垮索引遍历
        if len(q) > 40:
            q = q[:40]
        # 确保全市场证券名称索引可用（真实数据，来自行情服务器证券列表）
        self._ensure_name_index()
        results = []

        is_code_like = any(ch.isdigit() for ch in q)
        q_upper = q.upper().replace(".SH", "").replace(".SZ", "").replace(".BJ", "")
        q_upper = q_upper.replace("SH", "").replace("SZ", "").replace("BJ", "")

        if is_code_like:
            # 1) 代码形态：直接在全市场索引中精确匹配 + 前缀匹配
            candidates = [c.strip().upper() for c in q.replace("，", ",").replace(" ", ",").split(",") if c.strip()]
            for c in candidates:
                pc = c.replace(".SH", "").replace(".SZ", "").replace(".BJ", "")
                pc = pc.replace("SH", "").replace("SZ", "").replace("BJ", "")
                # 精确命中
                if pc in self._name_idx:
                    info = self._name_idx[pc]
                    results.append(self._idx_entry(pc, info))
                elif _is_index_code(pc):
                    # 指数在证券列表中常无名称，直接给出可读结果
                    results.append({
                        "code": pc,
                        "name": self._index_name(pc) or pc,
                        "market": "上海" if pc.startswith("9") else "深圳",
                        "kind": "指数",
                    })
                else:
                    # 前缀模糊（如输入 6005 补全 600519 等）
                    for code, info in self._name_idx.items():
                        if code.startswith(pc):
                            results.append(self._idx_entry(code, info))
                            if len(results) >= limit:
                                break
            # 若索引尚未就绪或未命中，回退到行情服务器实时验证单个代码
            if not results and candidates:
                results = self._verify_codes_realtime(candidates)
            # 场内仍查不到（如场外开放式基金），回退到 Tushare 基金列表兜底
            if not results and candidates:
                results = self._search_fund_list(candidates, by_code=True, limit=limit)
        else:
            # 2) 名称片段：在全市场索引中按名称模糊匹配
            frag = q
            for code, info in self._name_idx.items():
                if frag in info.get("name", ""):
                    results.append(self._idx_entry(code, info))
                    if len(results) >= limit * 3:
                        break
            # 索引不可用时回退内置名录
            if len(results) < limit:
                results += self._search_local_by_name(q, limit)
            # 同时在 Tushare 基金列表中按名称匹配（含场外基金）
            results += self._search_fund_list([q], by_code=False, limit=limit)

        # 去重，并过滤名称为空的脏结果（DEF-02：如指数在证券列表中 name 为空）
        seen, uniq = set(), []
        for r in results:
            key = r["code"]
            if key in seen:
                continue
            seen.add(key)
            # 名称兜底：指数给出可读名称；其余名称非空才保留
            if not r.get("name"):
                if _is_index_code(key):
                    r["name"] = self._index_name(key) or key
                else:
                    continue
            uniq.append(r)

        # 排序优先级：
        #   1. 代码精确命中 / 名称完全相等 最优先
        #   2. 类型权重：股票 > ETF/基金 > 可转债 > 其他
        #   3. 代码升序
        kind_weight = {"股票": 0, "ETF/基金": 1, "可转债": 2}

        def _rank(x):
            exact = 0 if (x["code"] == q_upper or x.get("name") == q) else 1
            kw = kind_weight.get(x.get("kind"), 3)
            return (exact, kw, x["code"])

        uniq.sort(key=_rank)
        return uniq[:limit]

    def _idx_entry(self, code, info):
        mkt = info.get("market")
        return {
            "code": code,
            "name": info.get("name", ""),
            "market": self._market_name.get(mkt, str(mkt)),
            "kind": self._infer_kind(code),
        }

    def _search_fund_list(self, queries, by_code=True, limit=20):
        """从 Tushare 基金列表兜底搜索（覆盖场外开放式基金）

        pytdx 行情站不含场外基金（如 161725、110011），这些标的需从该基金列表补充。
        尽量延迟导入 TushareClient，避免无 Tushare 环境时的硬依赖。

        Args:
            queries: list[str] 代码或名称片段列表
            by_code: True 按代码匹配；False 按名称片段匹配
            limit: 返回上限
        Returns:
            list[dict]: {code, name, market, kind}
        """
        try:
            from fund_estimation_system.data_fetcher.tushare_client import TushareClient
        except Exception:
            return self._search_fund_known(queries, by_code, limit)
        try:
            tc = TushareClient()
            # 同时拉取场内(E)与场外(O)基金，最大化覆盖
            df_e = tc.get_fund_list(market="E")
            df_o = tc.get_fund_list(market="O")
            import pandas as pd
            frames = [f for f in (df_e, df_o) if f is not None and not f.empty]
            if not frames:
                return self._search_fund_known(queries, by_code, limit)
            df = pd.concat(frames, ignore_index=True)
        except Exception:
            return self._search_fund_known(queries, by_code, limit)

        out = []
        seen = set()
        for q in queries:
            qk = str(q).strip().upper().replace(".SH", "").replace(".SZ", "").replace(".OF", "")
            qk = qk.replace("SH", "").replace("SZ", "").replace("OF", "")
            for _, row in df.iterrows():
                ts_code = str(row.get("ts_code", ""))
                name = str(row.get("name", ""))
                pure = ts_code.replace(".SH", "").replace(".SZ", "").replace(".OF", "")
                if by_code:
                    hit = (qk == pure.upper() or qk == ts_code.upper()
                           or (qk and pure.upper().startswith(qk)))
                else:
                    hit = q.lower() in name.lower() if name else False
                if not hit:
                    continue
                if pure in seen:
                    continue
                seen.add(pure)
                market = "上海" if ts_code.endswith(".SH") else ("深圳" if ts_code.endswith(".SZ") else "场外")
                out.append({
                    "code": pure,
                    "name": name,
                    "market": market,
                    "kind": "基金",
                })
                if len(out) >= limit:
                    return out
        # 真实基金列表不足（如演示模式仅少量模拟数据）时，追加内置常见基金名录
        if len(out) < limit:
            out += self._search_fund_known(queries, by_code, limit - len(out), seen)
        return out

    def _search_fund_known(self, queries, by_code=True, limit=20, seen=None):
        """内置常见基金名录兜底搜索（演示模式/无 Tushare 时可用）"""
        out = []
        seen = seen if seen is not None else set()
        for q in queries:
            qk = str(q).strip().upper()
            for code, name, mkt, kind in self._KNOWN_FUNDS:
                if by_code:
                    hit = (qk == code or (qk and code.startswith(qk)))
                else:
                    hit = q.lower() in name.lower()
                if not hit:
                    continue
                if code in seen:
                    continue
                seen.add(code)
                out.append({
                    "code": code,
                    "name": name,
                    "market": mkt,
                    "kind": kind,
                })
                if len(out) >= limit:
                    return out
        return out

    def _verify_codes_realtime(self, codes):
        """行情服务器实时验证代码（索引未就绪时的兜底），补全内置名称"""
        if not self._ensure_connection():
            return []
        pairs, idx_map = [], {}
        for c in codes:
            m, pure = _code_to_market(c)
            pairs.append((m, pure))
            idx_map[(m, pure)] = c
        try:
            raw = self._api.get_security_quotes(pairs)
        except Exception:
            raw = None
        out = []
        if raw:
            for r in raw:
                mkt, pure = r.get("market"), r.get("code")
                if pure is None:
                    continue
                # 仅当有价格或昨收时才认为是有效标的
                if not (float(r.get("price") or 0) > 0 or float(r.get("last_close") or 0) > 0):
                    continue
                name = (r.get("name") or "").strip() or self._known_name(pure)
                out.append({
                    "code": pure,
                    "name": name,
                    "market": self._market_name.get(mkt, str(mkt)),
                    "kind": self._infer_kind(pure),
                })
        return out

    def _infer_kind(self, code):
        c = str(code)
        if _is_index_code(c):
            return "指数"
        if c.startswith(("51", "15", "58", "56")):
            return "ETF/基金"
        if c.startswith(("16", "18")):
            return "LOF/基金"
        if c.startswith(("60", "68", "00", "30")):
            return "股票"
        if c.startswith(("11", "12")):
            return "可转债"
        return "标的"

    # 内置常见名录（真实存在的代表性标的，用于名称搜索补全/名称回退）
    # 股票/ETF（kind 由前缀推断即可）
    _KNOWN_STOCKS = [
        ("600519", "贵州茅台", "上海"), ("000858", "五粮液", "深圳"), ("300750", "宁德时代", "深圳"),
        ("601318", "中国平安", "上海"), ("000001", "平安银行", "深圳"), ("600036", "招商银行", "上海"),
        ("601166", "兴业银行", "上海"), ("600276", "恒瑞医药", "上海"), ("000333", "美的集团", "深圳"),
        ("000651", "格力电器", "深圳"), ("600030", "中信证券", "上海"), ("601398", "工商银行", "上海"),
        ("601888", "中国中免", "上海"), ("600887", "伊利股份", "上海"), ("002594", "比亚迪", "深圳"),
        ("600900", "长江电力", "上海"), ("601012", "隆基绿能", "上海"), ("600009", "上海机场", "上海"),
        ("000725", "京东方A", "深圳"), ("002415", "海康威视", "深圳"), ("510300", "沪深300ETF", "上海"),
        ("510500", "中证500ETF", "上海"), ("159915", "创业板ETF", "深圳"), ("512660", "军工ETF", "上海"),
        ("588000", "科创50ETF", "上海"), ("159919", "沪深300ETF", "深圳"), ("512010", "医药ETF", "上海"),
        ("512000", "券商ETF", "上海"), ("515030", "新能源ETF", "上海"), ("159995", "芯片ETF", "深圳"),
        ("159949", "创业板50ETF", "深圳"), ("512760", "芯片ETF", "上海"),
        ("511990", "华宝添益货币ETF", "上海"), ("518880", "黄金ETF", "上海"),
    ]
    # 基金专用名录（含 LOF、场外开放式基金，代码前缀与股票/可转债冲突，故显式标注 kind）
    _KNOWN_FUNDS = [
        ("161725", "招商中证白酒", "深圳", "LOF"), ("110011", "易方达中小盘", "场外", "场外基金"),
        ("001753", "招商丰庆混合", "场外", "场外基金"), ("110022", "易方达消费行业", "场外", "场外基金"),
        ("005827", "易方达蓝筹精选", "场外", "场外基金"), ("163406", "兴全合润", "深圳", "LOF"),
        ("161028", "富国中证煤炭", "深圳", "LOF"), ("160632", "鹏华酒", "深圳", "LOF"),
        ("161226", "国投瑞银白银", "深圳", "LOF"),
    ]

    def _known_name(self, code):
        c = str(code).replace(".SH", "").replace(".SZ", "").replace(".BJ", "")
        for kc, kn, _ in self._KNOWN_STOCKS:
            if kc == c:
                return kn
        for kc, kn, _, _ in self._KNOWN_FUNDS:
            if kc == c:
                return kn
        return ""

    _INDEX_NAMES = {
        "999999": "上证指数", "399001": "深证成指", "399006": "创业板指",
        "399005": "中小板指", "399300": "沪深300", "000300": "沪深300",
        "000016": "上证50", "000688": "科创50", "000905": "中证500",
    }

    def _index_name(self, code):
        c = str(code).replace(".SH", "").replace(".SZ", "").replace(".BJ", "")
        c = c.replace("SH", "").replace("SZ", "").replace("BJ", "")
        return self._INDEX_NAMES.get(c, "")

    def _search_local_by_name(self, name_frag, limit=20):
        """按名称片段在真实名录中模糊匹配（股票/ETF）"""
        frag = name_frag.lower()
        out = []
        for code, name, mkt in self._KNOWN_STOCKS:
            if frag in name.lower() or frag in code.lower():
                out.append({
                    "code": code,
                    "name": name,
                    "market": mkt,
                    "kind": self._infer_kind(code),
                })
        return out[:limit]

    def status(self):
        """状态信息（REQ-03：透出连接健康与陈旧状态，供前端强提醒）

        返回字段：
          - connected: 当前 socket 是否连通
          - stale: 是否陈旧（超过 STALE_THRESHOLD 秒无有效行情更新）
          - data_source: 数据源标识
          - last_success_at / last_error / reconnect_count: 自愈与可观测指标
        """
        connected = self._ensure_connection()
        now = time.time()
        # 断连或超阈值无有效更新，均视为陈旧（前端应强提醒，不可作为决策依据）
        stale = (not connected) or (now - self._last_success_at) > STALE_THRESHOLD
        return {
            "available": self.available,
            "pytdx_installed": PYTDX_AVAILABLE,
            "connected": connected,
            "stale": bool(stale),
            "data_source": self.name,
            "best_server": ":".join(map(str, self._best_server)) if self._best_server else None,
            "server_count": len(self.servers),
            "last_success_at": int(self._last_success_at) if self._last_success_at else None,
            "last_error": self._last_error,
            "reconnect_count": self._reconnect_count,
            "mode": ("实时行情(通达信行情服务器)" if connected
                     else "不可用"),
        }


# 全局单例（延迟连接）
_client = None
_client_lock = threading.Lock()


class AuthQuoteProvider(QuoteProvider):
    """授权/合规行情数据源（REQ-01 主源）。

    支持接入交易所 L1/L2、券商 PB 或商业数据商提供的 HTTP/REST 授权行情服务。
    通过环境变量配置（QUOTE_ENDPOINT / QUOTE_TOKEN），配置后即作为主源优先于
    pytdx 兜底源使用；未配置时 available=False，由 QuoteProviderHub 自动降级，
    并在 status() 中标记 degraded，前端据此强提醒。

    协议约定（授权源需实现的最小契约）：
      GET {endpoint}/quotes?codes=600519,000001  返回 {"data":[{code,name,price,...}]}
      GET {endpoint}/status                       返回 {"ok":true}
    鉴权：请求头 Authorization: Bearer {token}
    """

    name = "auth"

    def __init__(self, endpoint=None, token=None):
        self.endpoint = (endpoint or os.environ.get("QUOTE_ENDPOINT") or "").rstrip("/")
        self.token = token or os.environ.get("QUOTE_TOKEN", "")
        self._available = bool(self.endpoint and self.token)
        self._last_error = ("" if self._available
                            else "未配置授权行情源（QUOTE_ENDPOINT/QUOTE_TOKEN）")
        self._session_ok_at = 0
        self._lock = threading.Lock()
        try:
            import requests
            self._has_requests = True
        except ImportError:
            self._has_requests = False

    def _headers(self):
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    def _probe(self):
        """探测授权源可用性（带缓存，避免高频探测）。"""
        if not self._available or not self._has_requests:
            return False
        import time as _t
        now = _t.time()
        if now - self._session_ok_at < 10:
            return True
        try:
            import requests
            r = requests.get(f"{self.endpoint}/status", headers=self._headers(), timeout=4)
            ok = r.status_code == 200 and r.json().get("ok", True)
            if ok:
                self._session_ok_at = now
            else:
                self._last_error = f"授权源 /status 返回非 ok: {r.text[:120]}"
            return ok
        except Exception as e:
            self._last_error = f"授权源探测失败: {e}"
            return False

    def status(self):
        connected = self._probe()
        return {
            "available": self._available and connected,
            "connected": connected,
            "stale": not connected,
            "data_source": self.name,
            "endpoint": self.endpoint or None,
            "last_error": self._last_error,
            "reconnect_count": 0,
            "mode": ("授权行情源已接入(主源)" if (self._available and connected)
                     else "未启用(降级至 pytdx 兜底)"),
        }

    def _parse_remote(self, raw_list):
        """将授权源返回的标准化列表解析为与 TdxRealtimeClient 一致的结构。"""
        out = []
        for it in raw_list or []:
            try:
                price = float(it.get("price") or 0)
                last_close = float(it.get("last_close") or 0)
                out.append({
                    "code": str(it.get("code")),
                    "pure_code": str(it.get("code")),
                    "market": it.get("market", ""),
                    "name": it.get("name", ""),
                    "price": round(price, 3),
                    "last_close": round(last_close, 3),
                    "open": round(float(it.get("open") or 0), 3),
                    "high": round(float(it.get("high") or 0), 3),
                    "low": round(float(it.get("low") or 0), 3),
                    "volume": int(it.get("volume") or 0),
                    "amount": float(it.get("amount") or 0),
                    "bid1": round(float(it.get("bid1") or 0), 3),
                    "ask1": round(float(it.get("ask1") or 0), 3),
                    "bid_vol1": int(it.get("bid_vol1") or 0),
                    "ask_vol1": int(it.get("ask_vol1") or 0),
                    "servertime": it.get("servertime", ""),
                    "is_trading": price > 0,
                })
            except (TypeError, ValueError):
                continue
        return out

    def get_realtime_quotes(self, codes):
        if not self._available or not self._has_requests:
            return []
        try:
            import requests
            r = requests.get(f"{self.endpoint}/quotes",
                             params={"codes": ",".join(codes)},
                             headers=self._headers(), timeout=5)
            if r.status_code == 200:
                data = r.json().get("data", [])
                return self._parse_remote(data)
        except Exception as e:
            self._last_error = f"授权源拉取行情失败: {e}"
        return []

    def get_single_quote(self, code):
        res = self.get_realtime_quotes([code])
        return res[0] if res else None

    def get_minute_data(self, code):
        if not self._available or not self._has_requests:
            return []
        try:
            import requests
            r = requests.get(f"{self.endpoint}/minute",
                             params={"code": code},
                             headers=self._headers(), timeout=5)
            if r.status_code == 200:
                return r.json().get("data", [])
        except Exception:
            pass
        return []

    def get_kline(self, code, ktype="day", count=120):
        if not self._available or not self._has_requests:
            return []
        try:
            import requests
            r = requests.get(f"{self.endpoint}/kline",
                             params={"code": code, "ktype": ktype, "count": count},
                             headers=self._headers(), timeout=5)
            if r.status_code == 200:
                return r.json().get("data", [])
        except Exception:
            pass
        return []

    def search(self, query, limit=20):
        if not self._available or not self._has_requests:
            return []
        try:
            import requests
            r = requests.get(f"{self.endpoint}/search",
                             params={"q": query, "limit": limit},
                             headers=self._headers(), timeout=5)
            if r.status_code == 200:
                return r.json().get("data", [])
        except Exception:
            pass
        return []


class QuoteProviderHub(QuoteProvider):
    """多源行情管理器（REQ-01/REQ-03）：主源优先，断连自动切 fallback。

    主源（auth/授权）不可用时自动降级到 pytdx 兜底，并对外暴露当前实际
    使用的源与降级状态，便于前端在 UI 强提醒数据源变化（非静默切换）。
    """

    name = "hub"

    def __init__(self, primary=None, fallback=None):
        self.primary = primary or AuthQuoteProvider()
        self.fallback = fallback or TdxRealtimeClient()
        self._active = None  # 实际当前生效的源
        self._latency_ms = None       # 最近一次行情请求端到端延迟(ms)（REQ-01/REQ-07）
        self._latency_ewma = None     # 指数加权平均延迟，平滑抖动

    def _record_latency(self, ms):
        """记录行情端到端延迟(ms)，并做 EWMA 平滑（REQ-07 延迟可视化）。"""
        self._latency_ms = round(ms, 1)
        if self._latency_ewma is None:
            self._latency_ewma = ms
        else:
            self._latency_ewma = 0.7 * self._latency_ewma + 0.3 * ms

    def _active_provider(self):
        """选择当前生效数据源：主源可用则用主源，否则 fallback。

        关键防护（REQ-03 可用性）：若主源（授权源）已配置 endpoint/token（说明
        部署意图就是走授权源），但当前探测不可达，则**直接返回主源的离线/降级状态**，
        而**不降级到 pytdx 公网扫描**——避免 pytdx fallback 在公网不可达时长时间联网
        阻塞（逐服务器 4s 超时），导致所有调用 status() 的请求挂死。
        仅当主源完全未配置（_available=False，即环境本就打算用 pytdx）才走兜底。
        """
        try:
            ps = self.primary.status()
            if ps.get("available") and not ps.get("stale"):
                self._active = self.primary
                return self.primary
            # 主源已配置但不可达：不再降级到 pytdx 联网（避免阻塞），保持在主源离线态
            if self.primary._available:
                self._active = self.primary
                return self.primary
        except Exception:
            # 主源已配置却异常，同样保持在主源离线态，不触发 pytdx 联网
            if getattr(self.primary, "_available", False):
                self._active = self.primary
                return self.primary
        self._active = self.fallback
        return self.fallback

    def status(self):
        active = self._active_provider()
        s = active.status()
        s = dict(s)
        s["active_source"] = active.name
        # 降级判定：当前生效源不是主源（即授权源不可用、回退到兜底），则视为降级
        s["degraded"] = (active.name != self.primary.name)
        # REQ-07：透出端到端延迟(ms) 与数据源标识，供前端常驻展示与超阈值告警
        s["latency_ms"] = self._latency_ms
        s["latency_ewma_ms"] = round(self._latency_ewma, 1) if self._latency_ewma is not None else None
        s["latency_level"] = self._latency_level()
        return s

    def _latency_level(self):
        """延迟分级：good(<300ms)/warn(<1000ms)/bad(>=1000ms)，供前端变色。"""
        v = self._latency_ewma
        if v is None:
            return "unknown"
        if v < 300:
            return "good"
        if v < 1000:
            return "warn"
        return "bad"

    def get_realtime_quotes(self, codes):
        _t0 = time.time()
        result = self._active_provider().get_realtime_quotes(codes)
        self._record_latency((time.time() - _t0) * 1000.0)
        return result

    def get_single_quote(self, code):
        return self._active_provider().get_single_quote(code)

    def get_minute_data(self, code):
        return self._active_provider().get_minute_data(code)

    def get_kline(self, code, ktype="day", count=120):
        return self._active_provider().get_kline(code, ktype=ktype, count=count)

    def search(self, query, limit=20):
        return self._active_provider().search(query, limit=limit)


def get_client():
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                # 使用多源 Hub：主源为授权源（未配置时自动降级 pytdx）
                _client = QuoteProviderHub()
    return _client


if __name__ == "__main__":
    c = get_client()
    print("STATUS:", c.status())
    if c.status()["connected"]:
        q = c.get_realtime_quotes(["600519", "000001", "300750"])
        for x in q:
            print(x)
        print("MINUTE 600519:", len(c.get_minute_data("600519")))
        print("KLINE 600519:", len(c.get_kline("600519", "day", 5)))
