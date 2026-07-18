# -*- coding: utf-8 -*-
"""Tushare Pro 数据获取模块 - 中国公募基金 & A股"""
import os
import json
import pandas as pd
from datetime import datetime, timedelta

# 尝试导入 tushare
try:
    import tushare as ts
    TUSHARE_AVAILABLE = True
except ImportError:
    TUSHARE_AVAILABLE = False

from fund_estimation_system import config

CACHE_DIR = config.CACHE_DIR


class TushareClient:
    """Tushare Pro 客户端"""
    
    def __init__(self, token=None):
        self.token = token or config.TUSHARE_TOKEN
        self.pro = None
        self.demo_mode = config.DEMO_MODE
        
        if self.token and TUSHARE_AVAILABLE:
            ts.set_token(self.token)
            self.pro = ts.pro_api()
        elif not self.demo_mode:
            print("[WARN] Tushare token未配置，将使用演示模式。请设置环境变量 TUSHARE_TOKEN")
            self.demo_mode = True
    
    def _cache_path(self, name, suffix=".json"):
        return os.path.join(CACHE_DIR, f"{name}{suffix}")
    
    def _save_cache(self, name, df):
        path = self._cache_path(name, ".csv")
        df.to_csv(path, index=False, encoding="utf-8-sig")
    
    def _load_cache(self, name):
        path = self._cache_path(name, ".csv")
        if os.path.exists(path):
            return pd.read_csv(path)
        return None
    
    def _get_demo_fund_nav(self, ts_code, start_date=None, end_date=None, days=90):
        """无真实数据源时返回空（不捏造净值数据）

        说明: 在配置 TUSHARE_TOKEN 前，系统没有真实净值来源，
        此处严禁用随机数据伪造，直接返回空 DataFrame 由上层如实提示。
        """
        print(f"[INFO] 无真实净值数据源（未配置 TUSHARE_TOKEN），不生成模拟数据: {ts_code}")
        return pd.DataFrame()

    def get_fund_nav(self, ts_code, start_date=None, end_date=None, market=None):
        """获取基金净值数据"""
        if self.demo_mode or not self.pro:
            # 无真实数据源：返回空，绝不伪造
            return self._get_demo_fund_nav(ts_code, start_date, end_date)

        try:
            df = self.pro.fund_nav(
                ts_code=ts_code,
                start_date=start_date,
                end_date=end_date,
                market=market
            )
            if df is not None and not df.empty:
                self._save_cache(f"fund_nav_{ts_code}", df)
            return df
        except Exception as e:
            print(f"[ERROR] Tushare获取基金净值失败: {e}")
            # 真实源失败，返回空（不回退到模拟数据）
            return pd.DataFrame()
    
    def get_fund_list(self, market="E"):
        """获取基金列表"""
        if self.demo_mode or not self.pro:
            # 模拟基金列表
            data = [
                {"ts_code": "510300.SH", "name": "沪深300ETF", "fund_type": "股票型", "management": "华夏基金", "market": "E"},
                {"ts_code": "512000.SH", "name": "券商ETF", "fund_type": "股票型", "management": "华宝基金", "market": "E"},
                {"ts_code": "159915.SZ", "name": "创业板ETF", "fund_type": "股票型", "management": "易方达基金", "market": "E"},
                {"ts_code": "001753.OF", "name": "招商丰庆混合", "fund_type": "混合型", "management": "招商基金", "market": "O"},
                {"ts_code": "110022.OF", "name": "易方达消费行业", "fund_type": "股票型", "management": "易方达基金", "market": "O"},
            ]
            return pd.DataFrame(data)
        
        try:
            df = self.pro.fund_basic(market=market)
            return df
        except Exception as e:
            print(f"[ERROR] Tushare获取基金列表失败: {e}")
            return pd.DataFrame()
    
    def get_fund_portfolio(self, ts_code, period=None):
        """获取基金持仓（无真实源时返回空，不伪造持仓）"""
        if self.demo_mode or not self.pro:
            print(f"[INFO] 无真实持仓数据源（未配置 TUSHARE_TOKEN）: {ts_code}")
            return pd.DataFrame()

        try:
            df = self.pro.fund_portfolio(ts_code=ts_code, period=period)
            return df
        except Exception as e:
            print(f"[ERROR] Tushare获取基金持仓失败: {e}")
            return pd.DataFrame()
    
    def get_stock_list(self):
        """获取A股股票列表

        返回 DataFrame: ts_code, name, industry, market
        """
        if self.demo_mode or not self.pro:
            # 演示模式：内置 A股核心标的池（真实代码与名称）
            stocks = [
                ("600519.SH", "贵州茅台", "白酒", "主板"),
                ("000858.SZ", "五粮液", "白酒", "主板"),
                ("601318.SH", "中国平安", "保险", "主板"),
                ("600036.SH", "招商银行", "银行", "主板"),
                ("601166.SH", "兴业银行", "银行", "主板"),
                ("000001.SZ", "平安银行", "银行", "主板"),
                ("600276.SH", "恒瑞医药", "医药", "主板"),
                ("300750.SZ", "宁德时代", "电力设备", "创业板"),
                ("002594.SZ", "比亚迪", "汽车", "主板"),
                ("000333.SZ", "美的集团", "家电", "主板"),
                ("000651.SZ", "格力电器", "家电", "主板"),
                ("600900.SH", "长江电力", "电力", "主板"),
                ("601012.SH", "隆基绿能", "电力设备", "主板"),
                ("002415.SZ", "海康威视", "电子", "主板"),
                ("600887.SH", "伊利股份", "食品饮料", "主板"),
                ("601888.SH", "中国中免", "旅游零售", "主板"),
                ("600030.SH", "中信证券", "券商", "主板"),
                ("000002.SZ", "万科A", "房地产", "主板"),
                ("601398.SH", "工商银行", "银行", "主板"),
                ("600000.SH", "浦发银行", "银行", "主板"),
                ("300059.SZ", "东方财富", "券商", "创业板"),
                ("002230.SZ", "科大讯飞", "计算机", "主板"),
                ("688981.SH", "中芯国际", "半导体", "科创板"),
                ("603259.SH", "药明康德", "医药", "主板"),
                ("600585.SH", "海螺水泥", "建材", "主板"),
            ]
            return pd.DataFrame(stocks, columns=["ts_code", "name", "industry", "market"])

        try:
            df = self.pro.stock_basic(exchange="", list_status="L", fields="ts_code,name,industry,market")
            return df
        except Exception as e:
            print(f"[ERROR] Tushare获取股票列表失败: {e}")
            return pd.DataFrame()

    def get_stock_daily(self, ts_code, start_date=None, end_date=None):
        """获取A股日线行情

        无真实数据源（未配置 TUSHARE_TOKEN）时返回空，绝不伪造随机走势。
        真实数据优先级由上层（web_server）保证：TDX 实时 > Tushare。
        """
        if self.demo_mode or not self.pro:
            print(f"[INFO] 无真实行情源（未配置 TUSHARE_TOKEN），请用通达信实时行情: {ts_code}")
            return pd.DataFrame()

        try:
            df = self.pro.daily(ts_code=ts_code, start_date=start_date, end_date=end_date)
            return df
        except Exception as e:
            print(f"[ERROR] Tushare获取股票行情失败: {e}")
            return pd.DataFrame()


if __name__ == "__main__":
    client = TushareClient()
    print("=== 演示模式基金列表 ===")
    print(client.get_fund_list().head())
    print("\n=== 演示模式基金净值 ===")
    print(client.get_fund_nav("510300.SH", days=30).tail())
    print("\n=== 演示模式基金持仓 ===")
    print(client.get_fund_portfolio("001753.OF"))
