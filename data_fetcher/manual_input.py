# -*- coding: utf-8 -*-
"""手动持仓数据导入模块"""
import json
import pandas as pd
from datetime import datetime


class ManualPortfolio:
    """手动持仓管理"""
    
    def __init__(self, data_path=None):
        self.data_path = data_path
        self.holdings = []
    
    def load_from_json(self, json_path):
        """从JSON文件加载持仓"""
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.holdings = data.get("holdings", [])
        return self.holdings
    
    def load_from_dict(self, data):
        """从字典加载持仓
        
        data格式:
        {
            "holdings": [
                {"code": "510300.SH", "name": "沪深300ETF", "type": "cn_fund", "shares": 1000, "cost": 3.5},
                {"code": "SPY", "name": "SPDR S&P 500", "type": "us_fund", "shares": 50, "cost": 450},
                {"code": "000001.SZ", "name": "平安银行", "type": "cn_stock", "shares": 500, "cost": 12.0},
            ]
        }
        """
        self.holdings = data.get("holdings", [])
        return self.holdings
    
    def add_holding(self, code, name, asset_type, shares, cost_price, market="CN"):
        """添加单条持仓
        
        Args:
            code: 代码
            name: 名称
            asset_type: cn_fund(中国公募), us_fund(海外基金), cn_stock(A股), hk_stock(港股)
            shares: 份额/股数
            cost_price: 成本价
            market: 市场
        """
        self.holdings.append({
            "code": code,
            "name": name,
            "type": asset_type,
            "shares": float(shares),
            "cost_price": float(cost_price),
            "market": market,
            "added_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })
    
    def to_dataframe(self):
        """转为DataFrame"""
        if not self.holdings:
            return pd.DataFrame(columns=["code", "name", "type", "shares", "cost_price", "market"])
        return pd.DataFrame(self.holdings)
    
    def get_summary(self):
        """获取持仓摘要"""
        df = self.to_dataframe()
        if df.empty:
            return {}
        return {
            "total_holdings": len(df),
            "by_type": df.groupby("type")["shares"].count().to_dict(),
            "by_market": df.groupby("market")["shares"].count().to_dict(),
        }


if __name__ == "__main__":
    mp = ManualPortfolio()
    mp.add_holding("510300.SH", "沪深300ETF", "cn_fund", 1000, 3.5, "CN")
    mp.add_holding("SPY", "SPDR S&P 500", "us_fund", 50, 450, "US")
    mp.add_holding("000001.SZ", "平安银行", "cn_stock", 500, 12.0, "CN")
    
    print("=== 持仓数据 ===")
    print(mp.to_dataframe())
    print("\n=== 持仓摘要 ===")
    print(mp.get_summary())
