"""基金代码索引：从 data/fund_codes.json 加载全市场基金代码-名称映射。

数据来源：证券之星「全市场开放式基金」代码速查页
（https://fund.stockstar.com/funds/fundallcode.htm），离线抓取得到，
作为 Tushare / 本地通达信数据缺失时的兜底字典。

仅含静态「代码-名称」映射，不含任何行情/净值数据，不违背「无数据不捏造」原则。
"""

import json
import os

_DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "fund_codes.json")

_cache = None


def load_fund_codes():
    """返回原始列表 [{"code": "161725", "name": "..."}, ...]（带缓存）"""
    global _cache
    if _cache is not None:
        return _cache
    try:
        with open(_DATA_PATH, "r", encoding="utf-8") as f:
            data = json.load(f) or []
    except Exception:
        data = []
    _cache = data
    return _cache


def _infer_market(code):
    """依据代码前缀粗略推断市场（仅用于兜底展示，不用于行情路由）"""
    if code.startswith(("50", "51", "52", "55", "56", "60")):
        return "上海"
    return "深圳"


def as_builtin_funds():
    """转换为 fund_bp.BUILTIN_FUNDS 同构的字典列表"""
    out = []
    for it in load_fund_codes():
        code = str(it.get("code", "")).strip()
        name = str(it.get("name", "")).strip()
        if not code or not name:
            continue
        out.append({
            "code": code,
            "name": name,
            "kind": "基金",
            "detail": "证券之星名录",
            "market": "E",
        })
    return out


def as_known_funds():
    """转换为 tdx_realtime._KNOWN_FUNDS 同构的元组列表 (code, name, market, kind)"""
    out = []
    for it in load_fund_codes():
        code = str(it.get("code", "")).strip()
        name = str(it.get("name", "")).strip()
        if not code or not name:
            continue
        out.append((code, name, _infer_market(code), "基金"))
    return out
