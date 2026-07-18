# -*- coding: utf-8 -*-
"""基金组合收益估算模块"""
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from fund_estimation_system.data_fetcher.tushare_client import TushareClient
from fund_estimation_system.data_fetcher.yahoo_client import YahooClient
from fund_estimation_system.data_fetcher.manual_input import ManualPortfolio


class PortfolioCalculator:
    """投资组合计算器
    
    功能:
    - 计算持仓市值
    - 计算收益率（总收益、年化收益）
    - 计算最大回撤
    - 计算夏普比率（简化版）
    - 资产配置分析
    """
    
    def __init__(self, tushare_token=None):
        self.ts_client = TushareClient(token=tushare_token)
        self.yh_client = YahooClient()
        self.manual = ManualPortfolio()
    
    def get_current_price(self, code, asset_type):
        """获取当前价格/净值"""
        if asset_type in ["cn_fund", "cn_stock"]:
            end_date = datetime.now().strftime("%Y%m%d")
            start_date = (datetime.now() - timedelta(days=5)).strftime("%Y%m%d")
            if asset_type == "cn_fund":
                df = self.ts_client.get_fund_nav(code, start_date=start_date, end_date=end_date)
                if df is not None and not df.empty:
                    return float(df["unit_nav"].iloc[0])
            else:
                df = self.ts_client.get_stock_daily(code, start_date=start_date, end_date=end_date)
                if df is not None and not df.empty:
                    return float(df["close"].iloc[0])
        elif asset_type == "us_fund":
            df = self.yh_client.get_ticker_data(code, period="5d")
            if df is not None and not df.empty:
                return float(df["Close"].iloc[-1])
        return 0.0
    
    def calculate_portfolio(self, holdings):
        """计算组合总览
        
        Args:
            holdings: list of dict, [{code, name, type, shares, cost_price, market}, ...]
        
        Returns:
            dict: 组合分析结果
        """
        if not holdings:
            return {"error": "无持仓数据"}
        
        total_cost = 0
        total_value = 0
        items = []
        
        for h in holdings:
            code = h["code"]
            asset_type = h["type"]
            shares = float(h["shares"])
            cost_price = float(h["cost_price"])
            
            current_price = self.get_current_price(code, asset_type)
            cost_value = shares * cost_price
            market_value = shares * current_price if current_price else 0
            profit = market_value - cost_value
            profit_pct = (profit / cost_value * 100) if cost_value != 0 else 0
            
            total_cost += cost_value
            total_value += market_value
            
            items.append({
                "code": code,
                "name": h.get("name", code),
                "type": asset_type,
                "market": h.get("market", "CN"),
                "shares": shares,
                "cost_price": cost_price,
                "current_price": round(current_price, 4) if current_price else None,
                "cost_value": round(cost_value, 2),
                "market_value": round(market_value, 2),
                "profit": round(profit, 2),
                "profit_pct": round(profit_pct, 2),
                "weight": 0,  # 稍后计算
            })
        
        # 计算权重
        for item in items:
            if total_value > 0:
                item["weight"] = round(item["market_value"] / total_value * 100, 2)
        
        total_profit = total_value - total_cost
        total_profit_pct = (total_profit / total_cost * 100) if total_cost != 0 else 0
        
        # 按类型统计
        type_summary = {}
        for item in items:
            t = item["type"]
            if t not in type_summary:
                type_summary[t] = {"cost": 0, "value": 0, "profit": 0}
            type_summary[t]["cost"] += item["cost_value"]
            type_summary[t]["value"] += item["market_value"]
            type_summary[t]["profit"] += item["profit"]
        
        for t in type_summary:
            type_summary[t]["profit_pct"] = round(
                (type_summary[t]["profit"] / type_summary[t]["cost"] * 100), 2
            ) if type_summary[t]["cost"] else 0
            type_summary[t]["weight"] = round(
                type_summary[t]["value"] / total_value * 100, 2
            ) if total_value else 0
        
        return {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "total_cost": round(total_cost, 2),
            "total_value": round(total_value, 2),
            "total_profit": round(total_profit, 2),
            "total_profit_pct": round(total_profit_pct, 2),
            "holdings": items,
            "type_summary": type_summary,
        }
    
    def calculate_historical_returns(self, fund_code, fund_type="cn", period_days=252):
        """计算历史收益率指标"""
        if fund_type == "cn":
            end_date = datetime.now().strftime("%Y%m%d")
            start_date = (datetime.now() - timedelta(days=period_days + 30)).strftime("%Y%m%d")
            df = self.ts_client.get_fund_nav(fund_code, start_date=start_date, end_date=end_date)
            if df is None or df.empty:
                return {}
            navs = df["unit_nav"].astype(float).values[::-1]  # 正序
        else:
            df = self.yh_client.get_ticker_data(fund_code, period=f"{period_days+30}d")
            if df is None or df.empty:
                return {}
            navs = df["Close"].values
        
        if len(navs) < 2:
            return {}
        
        # 日收益率
        daily_returns = np.diff(navs) / navs[:-1]
        
        # 总收益率
        total_return = (navs[-1] - navs[0]) / navs[0] * 100
        
        # 年化收益率 (按252个交易日)
        years = len(navs) / 252
        annual_return = ((navs[-1] / navs[0]) ** (1 / years) - 1) * 100 if years > 0 else 0
        
        # 年化波动率
        annual_vol = np.std(daily_returns) * np.sqrt(252) * 100
        
        # 最大回撤
        cummax = np.maximum.accumulate(navs)
        drawdowns = (navs - cummax) / cummax
        max_drawdown = np.min(drawdowns) * 100
        
        # 夏普比率 (简化，假设无风险利率2%)
        risk_free_rate = 0.02
        sharpe = ((annual_return / 100 - risk_free_rate) / (annual_vol / 100)) if annual_vol != 0 else 0
        
        return {
            "total_return_pct": round(total_return, 2),
            "annual_return_pct": round(annual_return, 2),
            "annual_volatility_pct": round(annual_vol, 2),
            "max_drawdown_pct": round(max_drawdown, 2),
            "sharpe_ratio": round(sharpe, 3),
            "period_days": len(navs),
        }
    
    def _get_nav_series(self, code, asset_type, period_days=252):
        """获取单资产的净值序列（正序），用于历史回测"""
        if asset_type in ["cn_fund", "cn", "cn_stock"]:
            end_date = datetime.now().strftime("%Y%m%d")
            start_date = (datetime.now() - timedelta(days=period_days + 30)).strftime("%Y%m%d")
            if asset_type == "cn_stock":
                df = self.ts_client.get_stock_daily(code, start_date=start_date, end_date=end_date)
                if df is not None and not df.empty:
                    df = df.sort_values("trade_date")
                    return df["close"].astype(float).values
            else:
                df = self.ts_client.get_fund_nav(code, start_date=start_date, end_date=end_date)
                if df is not None and not df.empty:
                    df = df.sort_values("nav_date")
                    return df["unit_nav"].astype(float).values
        else:
            df = self.yh_client.get_ticker_data(code, period=f"{period_days + 30}d")
            if df is not None and not df.empty:
                return df["Close"].astype(float).values
        return None

    def simulate_portfolio_history(self, holdings, period_days=252):
        """回测组合历史走势（按市值权重合成真实净值曲线）

        对齐各资产净值序列长度后，以各持仓当前市值权重（初始固定权重）
        合成归一化组合净值曲线，并计算组合级风险收益指标。

        Returns:
            dict: 组合净值曲线 + 收益/风险指标
        """
        # 1. 计算各持仓市值权重（基于成本市值）
        weighted = []
        for h in holdings:
            code = h["code"]
            asset_type = h["type"]
            navs = self._get_nav_series(code, asset_type, period_days)
            if navs is None or len(navs) < 2:
                continue
            cost_value = float(h.get("shares", 0)) * float(h.get("cost_price", 0))
            weighted.append({
                "code": code,
                "name": h.get("name", code),
                "navs": np.asarray(navs, dtype=float),
                "weight_raw": cost_value if cost_value > 0 else 1.0,
            })

        if not weighted:
            return {"error": "无法获取任何资产的历史数据"}

        # 2. 对齐长度（取最短序列）
        min_len = min(len(w["navs"]) for w in weighted)
        min_len = max(min_len, 2)

        # 3. 归一化权重
        total_w = sum(w["weight_raw"] for w in weighted)
        for w in weighted:
            w["weight"] = w["weight_raw"] / total_w if total_w else 1.0 / len(weighted)

        # 4. 合成归一化组合净值曲线
        portfolio_curve = np.zeros(min_len)
        for w in weighted:
            series = w["navs"][-min_len:]
            normalized = series / series[0]
            portfolio_curve += w["weight"] * normalized

        # 5. 计算组合级指标
        daily_returns = np.diff(portfolio_curve) / portfolio_curve[:-1]
        total_return = (portfolio_curve[-1] - portfolio_curve[0]) / portfolio_curve[0] * 100
        years = min_len / 252
        annual_return = ((portfolio_curve[-1] / portfolio_curve[0]) ** (1 / years) - 1) * 100 if years > 0 else 0
        annual_vol = np.std(daily_returns) * np.sqrt(252) * 100
        cummax = np.maximum.accumulate(portfolio_curve)
        max_drawdown = np.min((portfolio_curve - cummax) / cummax) * 100
        risk_free_rate = 0.02
        sharpe = ((annual_return / 100 - risk_free_rate) / (annual_vol / 100)) if annual_vol != 0 else 0

        return {
            "period_days": int(min_len),
            "total_return_pct": round(total_return, 2),
            "annual_return_pct": round(annual_return, 2),
            "annual_volatility_pct": round(annual_vol, 2),
            "max_drawdown_pct": round(max_drawdown, 2),
            "sharpe_ratio": round(sharpe, 3),
            "curve": [round(float(v), 4) for v in portfolio_curve],
            "weights": {w["code"]: round(w["weight"] * 100, 2) for w in weighted},
            "note": "按初始市值权重合成的归一化组合净值曲线（未考虑再平衡）",
        }


if __name__ == "__main__":
    calc = PortfolioCalculator()
    
    # 测试持仓
    holdings = [
        {"code": "510300.SH", "name": "沪深300ETF", "type": "cn_fund", "shares": 1000, "cost_price": 3.5, "market": "CN"},
        {"code": "SPY", "name": "SPDR S&P 500", "type": "us_fund", "shares": 50, "cost_price": 450, "market": "US"},
        {"code": "000001.SZ", "name": "平安银行", "type": "cn_stock", "shares": 500, "cost_price": 12.0, "market": "CN"},
    ]
    
    print("=== 组合收益估算 ===")
    result = calc.calculate_portfolio(holdings)
    print(f"总成本: {result['total_cost']}")
    print(f"总市值: {result['total_value']}")
    print(f"总收益: {result['total_profit']} ({result['total_profit_pct']}%)")
    print(f"\n持仓明细:")
    for item in result["holdings"]:
        print(f"  {item['name']}: 成本{item['cost_value']}, 市值{item['market_value']}, 收益{item['profit_pct']}%")
    
    print(f"\n资产分类:")
    for t, s in result["type_summary"].items():
        print(f"  {t}: 权重{s['weight']}%, 收益{s['profit_pct']}%")
    
    print("\n=== 历史指标 ===")
    hist = calc.calculate_historical_returns("510300.SH", "cn", 252)
    print(f"沪深300ETF: 年化收益{hist.get('annual_return_pct')}%, 最大回撤{hist.get('max_drawdown_pct')}%, 夏普{hist.get('sharpe_ratio')}")
