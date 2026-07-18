# -*- coding: utf-8 -*-
"""Yahoo Finance 数据获取模块 - 海外/美股基金"""
import os
import pandas as pd
from datetime import datetime, timedelta

try:
    import yfinance as yf
    YFINANCE_AVAILABLE = True
except ImportError:
    YFINANCE_AVAILABLE = False

from fund_estimation_system import config

CACHE_DIR = config.CACHE_DIR


class YahooClient:
    """Yahoo Finance 客户端"""
    
    def __init__(self):
        self.demo_mode = not YFINANCE_AVAILABLE
        if self.demo_mode:
            print("[WARN] yfinance未安装，海外基金将使用演示模式。运行: pip install yfinance")
    
    @staticmethod
    def _parse_period_days(period):
        """将 yfinance period 字符串解析为天数

        支持: '30d', '90d', '252d', '1mo', '3mo', '6mo', '1y', '2y', '5y', 'ytd', 'max'
        """
        if not period:
            return 90
        p = str(period).strip().lower()
        try:
            if p.endswith("d"):
                return max(int(p[:-1]), 5)
            if p.endswith("mo"):
                return int(p[:-2]) * 30
            if p.endswith("y"):
                return int(p[:-1]) * 365
        except ValueError:
            pass
        mapping = {"ytd": 200, "max": 365 * 5}
        return mapping.get(p, 90)

    def _get_demo_data(self, ticker, period="90d", interval="1d"):
        """无真实数据源（yfinance 不可用/限流）时返回空，绝不伪造"""
        print(f"[INFO] 无真实海外行情源（yfinance 不可用），不生成模拟数据: {ticker}")
        return pd.DataFrame()
    
    def _cache_path(self, ticker, interval):
        safe = str(ticker).replace("/", "_").replace("\\", "_")
        return os.path.join(CACHE_DIR, f"yahoo_{safe}_{interval}.csv")

    def _save_cache(self, ticker, interval, df):
        try:
            df.to_csv(self._cache_path(ticker, interval), encoding="utf-8-sig")
        except Exception:
            pass

    def _load_cache(self, ticker, interval):
        path = self._cache_path(ticker, interval)
        if os.path.exists(path):
            try:
                df = pd.read_csv(path, index_col=0, parse_dates=True)
                if not df.empty:
                    return df
            except Exception:
                pass
        return None

    def get_ticker_data(self, ticker, period="1y", interval="1d"):
        """获取基金/股票历史数据
        
        Args:
            ticker: 如 SPY, VOO, QQQ, VTI, GLD, VXUS, EEM
            period: 1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, ytd, max
            interval: 1d, 1wk, 1mo
        
        数据源优先级: 实时 Yahoo -> 本地缓存 -> 模拟数据
        """
        if self.demo_mode:
            return self._get_demo_data(ticker, period, interval)
        
        try:
            t = yf.Ticker(ticker)
            df = t.history(period=period, interval=interval)
            if df is not None and not df.empty:
                self._save_cache(ticker, interval, df)
                return df
        except Exception as e:
            print(f"[ERROR] Yahoo Finance获取数据失败 ({ticker}): {e}")
        
        # 回退到本地缓存
        cached = self._load_cache(ticker, interval)
        if cached is not None:
            need = self._parse_period_days(period)
            print(f"[INFO] 使用本地缓存数据 ({ticker})")
            return cached.tail(need) if len(cached) > need else cached
        
        # 最终回退到模拟数据
        return self._get_demo_data(ticker, period, interval)
    
    def get_info(self, ticker):
        """获取基金基本信息"""
        if self.demo_mode:
            return {
                "shortName": f"{ticker} Fund (Demo)",
                "category": "Large Blend",
                "expenseRatio": 0.0003,
                "totalAssets": 1e10,
                "morningStarOverallRating": 4,
            }
        
        try:
            t = yf.Ticker(ticker)
            info = t.info
            return {
                "shortName": info.get("shortName", ticker),
                "category": info.get("category", "N/A"),
                "expenseRatio": info.get("expenseRatio", 0),
                "totalAssets": info.get("totalAssets", 0),
                "morningStarOverallRating": info.get("morningStarOverallRating", 0),
            }
        except Exception as e:
            print(f"[ERROR] Yahoo Finance获取信息失败 ({ticker}): {e}")
            return self.get_info(ticker)  # fallback


if __name__ == "__main__":
    client = YahooClient()
    print("=== SPY 演示数据 ===")
    print(client.get_ticker_data("SPY", period="30d").tail())
    print("\n=== SPY 基本信息 ===")
    print(client.get_info("SPY"))
