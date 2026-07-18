# -*- coding: utf-8 -*-
"""共享数据访问层（DAL）。

集中封装各业务域路由里反复出现的「取历史净值/价格序列」样板：
- 日期区间换算
- Tushare / Yahoo 双源切换
- 空值/异常兜底

目标：消除 web_server 中 7+ 处重复的 get_fund_nav + timedelta + 排序代码，
使路由层只关心「要什么数据」，而非「怎么拿」。
"""
from datetime import datetime, timedelta

from fund_estimation_system.data_fetcher.tushare_client import TushareClient
from fund_estimation_system.data_fetcher.yahoo_client import YahooClient
from fund_estimation_system.estimator.fund_nav_estimator import FundNavEstimator

_ts = TushareClient()
_yh = YahooClient()


def nav_series(code, fund_type, period_days, ts_client=None, yh_client=None):
    """取单标的归一化净值/价格序列（正序）。

    返回 (dates, navs)；任一为 None 表示取数失败。
    cn 走 Tushare 基金净值；其他走 Yahoo Close。
    内部已做排序与日期区间换算，调用方无需重复处理。
    """
    ts = ts_client or _ts
    yh = yh_client or _yh
    if fund_type == "cn":
        end = datetime.now().strftime("%Y%m%d")
        start = (datetime.now() - timedelta(days=period_days + 30)).strftime("%Y%m%d")
        df = ts.get_fund_nav(code, start_date=start, end_date=end)
        if df is not None and not df.empty:
            df = df.sort_values("nav_date")
            return df["nav_date"].astype(str).tolist(), df["unit_nav"].astype(float).tolist()
    else:
        df = yh.get_ticker_data(code, period=f"{period_days + 30}d")
        if df is not None and not df.empty:
            df = df.reset_index()
            dates = df["Date"].astype(str).tolist() if "Date" in df.columns else list(range(len(df)))
            return [str(d) for d in dates], df["Close"].astype(float).tolist()
    return None, None


def cn_nav_df(code, period_days, ts_client=None):
    """取 cn 基金净值 DataFrame（正序，含 nav_date/unit_nav），失败返回 None。"""
    ts = ts_client or _ts
    end = datetime.now().strftime("%Y%m%d")
    start = (datetime.now() - timedelta(days=period_days)).strftime("%Y%m%d")
    df = ts.get_fund_nav(code, start_date=start, end_date=end)
    if df is not None and not df.empty:
        return df.sort_values("nav_date")
    return None


def us_price_df(code, period_days, yh_client=None):
    """取海外标的 OHLCV DataFrame（含 Date/Open/High/Low/Close/Volume），失败返回 None。"""
    yh = yh_client or _yh
    df = yh.get_ticker_data(code, period=f"{period_days}d")
    if df is not None and not df.empty:
        return df.reset_index()
    return None


def date_range(period_days):
    """返回 (start, end) 字符串元组，避免各路由重复写 timedelta 换算。"""
    end = datetime.now().strftime("%Y%m%d")
    start = (datetime.now() - timedelta(days=period_days)).strftime("%Y%m%d")
    return start, end
