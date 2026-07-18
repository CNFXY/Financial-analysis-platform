# -*- coding: utf-8 -*-
"""基金风险分析模块 - 基于 fund-risk-analyzer Skill

功能:
- 年化收益率
- 最大回撤
- 夏普比率
- 年化波动率
- 相关性矩阵
- 卡玛比率 (Calmar Ratio)
- 索提诺比率 (Sortino Ratio)
- 下行偏差
- 阿尔法 / 贝塔
"""
import numpy as np
import pandas as pd
from datetime import datetime, timedelta


class FundRiskAnalyzer:
    """基金风险分析引擎"""

    TRADING_DAYS_PER_YEAR = 252  # A股年化交易日

    def __init__(self, risk_free_rate=0.02):
        """
        Args:
            risk_free_rate: 年化无风险利率，默认 2%（中国国债收益率）
        """
        self.risk_free_rate = risk_free_rate

    # ==================== 基础收益率计算 ====================
    @staticmethod
    def calculate_daily_returns(nav_series):
        """计算日收益率序列"""
        navs = np.asarray(nav_series, dtype=float)
        if len(navs) < 2:
            return np.array([])
        return np.diff(navs) / navs[:-1]

    @staticmethod
    def calculate_total_return(nav_series):
        """总收益率 (%)"""
        navs = np.asarray(nav_series, dtype=float)
        if len(navs) < 2:
            return 0.0
        return (navs[-1] - navs[0]) / navs[0] * 100

    @staticmethod
    def calculate_annualized_return(nav_series, trading_days=252):
        """年化收益率 (%)
        
        Ann. Return = (NAV_end / NAV_start) ^ (trading_days / n_days) - 1
        """
        navs = np.asarray(nav_series, dtype=float)
        if len(navs) < 2:
            return 0.0
        n_days = len(navs) - 1
        total_return = navs[-1] / navs[0]
        ann_return = (total_return ** (trading_days / n_days) - 1) * 100
        return ann_return

    # ==================== 波动率 ====================
    @staticmethod
    def calculate_annualized_volatility(daily_returns, trading_days=252):
        """年化波动率 (%)"""
        if len(daily_returns) < 2:
            return 0.0
        return np.std(daily_returns) * np.sqrt(trading_days) * 100

    @staticmethod
    def calculate_downside_deviation(daily_returns, target=0):
        """下行偏差（只统计低于目标的收益）"""
        downside = daily_returns[daily_returns < target]
        if len(downside) < 2:
            return 0.0
        return np.std(downside) * np.sqrt(252) * 100

    # ==================== 最大回撤 ====================
    @staticmethod
    def calculate_max_drawdown(nav_series):
        """最大回撤 (%)
        
        MDD = max((peak - trough) / peak)
        """
        navs = np.asarray(nav_series, dtype=float)
        if len(navs) < 2:
            return 0.0
        
        peak = np.maximum.accumulate(navs)
        drawdowns = (navs - peak) / peak
        max_dd = np.min(drawdowns)
        
        # 找到最大回撤区间
        trough_idx = np.argmin(drawdowns)
        peak_idx = np.argmax(navs[:trough_idx + 1]) if trough_idx > 0 else 0
        
        return {
            "max_drawdown_pct": round(max_dd * 100, 2),
            "peak_value": round(navs[peak_idx], 4),
            "trough_value": round(navs[trough_idx], 4),
            "peak_idx": int(peak_idx),
            "trough_idx": int(trough_idx),
        }

    @staticmethod
    def calculate_drawdown_series(nav_series):
        """计算回撤序列，用于绘制回撤曲线"""
        navs = np.asarray(nav_series, dtype=float)
        if len(navs) < 2:
            return np.array([])
        peak = np.maximum.accumulate(navs)
        return (navs - peak) / peak * 100

    # ==================== 夏普比率 ====================
    def calculate_sharpe_ratio(self, daily_returns, trading_days=252):
        """夏普比率
        
        Sharpe = (Annualized Return - Risk-Free Rate) / Annualized Volatility
        """
        if len(daily_returns) < 2:
            return 0.0
        ann_return = np.mean(daily_returns) * trading_days
        ann_vol = np.std(daily_returns) * np.sqrt(trading_days)
        if ann_vol == 0:
            return 0.0
        return (ann_return - self.risk_free_rate) / ann_vol

    # ==================== 索提诺比率 ====================
    def calculate_sortino_ratio(self, daily_returns, trading_days=252):
        """索提诺比率 (只考虑下行风险)"""
        if len(daily_returns) < 2:
            return 0.0
        ann_return = np.mean(daily_returns) * trading_days
        downside_dev = FundRiskAnalyzer.calculate_downside_deviation(daily_returns)
        if downside_dev == 0:
            return 0.0
        return (ann_return - self.risk_free_rate) / (downside_dev / 100)

    # ==================== 卡玛比率 ====================
    def calculate_calmar_ratio(self, nav_series, trading_days=252):
        """卡玛比率 = 年化收益率 / |最大回撤|"""
        ann_return = self.calculate_annualized_return(nav_series, trading_days) / 100
        mdd = self.calculate_max_drawdown(nav_series)
        max_dd_abs = abs(mdd["max_drawdown_pct"]) / 100
        if max_dd_abs == 0:
            return 0.0
        return (ann_return - self.risk_free_rate) / max_dd_abs

    # ==================== 阿尔法 / 贝塔 ====================
    @staticmethod
    def calculate_alpha_beta(fund_returns, benchmark_returns):
        """计算阿尔法和贝塔系数
        
        Args:
            fund_returns: 基金日收益率数组
            benchmark_returns: 基准日收益率数组
        
        Returns:
            dict: {alpha, beta, correlation, r_squared}
        """
        if len(fund_returns) != len(benchmark_returns) or len(fund_returns) < 2:
            return {"alpha": 0, "beta": 0, "correlation": 0, "r_squared": 0}
        
        covariance = np.cov(fund_returns, benchmark_returns)[0, 1]
        benchmark_var = np.var(benchmark_returns)
        beta = covariance / benchmark_var if benchmark_var != 0 else 0
        
        alpha = np.mean(fund_returns) - beta * np.mean(benchmark_returns)
        
        correlation = np.corrcoef(fund_returns, benchmark_returns)[0, 1]
        r_squared = correlation ** 2
        
        return {
            "alpha": round(alpha * 252, 4),  # 年化阿尔法
            "beta": round(beta, 4),
            "correlation": round(correlation, 4),
            "r_squared": round(r_squared, 4),
        }

    # ==================== 相关性矩阵 ====================
    @staticmethod
    def calculate_correlation_matrix(nav_dict):
        """计算多基金相关性矩阵
        
        Args:
            nav_dict: dict, {fund_name: nav_series}
        
        Returns:
            DataFrame: 相关性矩阵
        """
        returns_dict = {}
        for name, navs in nav_dict.items():
            if len(navs) >= 2:
                returns_dict[name] = np.diff(navs) / navs[:-1]
        
        if len(returns_dict) < 2:
            return pd.DataFrame()
        
        # 对齐长度（取最短）
        min_len = min(len(v) for v in returns_dict.values())
        aligned = {k: v[-min_len:] for k, v in returns_dict.items()}
        
        df = pd.DataFrame(aligned)
        return df.corr()

    # ==================== 综合风险分析 ====================
    def analyze_single_fund(self, nav_series, name="基金", benchmark_navs=None):
        """对单只基金进行完整风险分析
        
        Args:
            nav_series: 净值序列
            name: 基金名称
            benchmark_navs: 可选基准净值序列
        
        Returns:
            dict: 完整分析结果
        """
        navs = np.asarray(nav_series, dtype=float)
        if len(navs) < 2:
            return {"error": "数据不足"}
        
        daily_returns = self.calculate_daily_returns(navs)
        
        result = {
            "fund_name": name,
            "data_points": len(navs),
            "period_days": len(navs) - 1,
            # 收益率
            "total_return_pct": round(self.calculate_total_return(navs), 2),
            "annualized_return_pct": round(self.calculate_annualized_return(navs), 2),
            # 风险
            "annualized_volatility_pct": round(self.calculate_annualized_volatility(daily_returns), 2),
            "max_drawdown": self.calculate_max_drawdown(navs),
            "downside_deviation_pct": round(self.calculate_downside_deviation(daily_returns), 2),
            # 风险调整收益
            "sharpe_ratio": round(self.calculate_sharpe_ratio(daily_returns), 3),
            "sortino_ratio": round(self.calculate_sortino_ratio(daily_returns), 3),
            "calmar_ratio": round(self.calculate_calmar_ratio(navs), 3),
            # 日收益统计
            "daily_return_mean_pct": round(np.mean(daily_returns) * 100, 4),
            "daily_return_std_pct": round(np.std(daily_returns) * 100, 4),
            "positive_days_pct": round(np.sum(daily_returns > 0) / len(daily_returns) * 100, 1),
            "negative_days_pct": round(np.sum(daily_returns < 0) / len(daily_returns) * 100, 1),
        }
        
        # 基准对比
        if benchmark_navs is not None and len(benchmark_navs) >= len(navs):
            bench_returns = self.calculate_daily_returns(benchmark_navs[-len(navs):])
            if len(bench_returns) == len(daily_returns):
                ab = self.calculate_alpha_beta(daily_returns, bench_returns)
                result["alpha_beta"] = ab
        
        return result

    def analyze_portfolio(self, nav_dict, portfolio_weights=None):
        """分析投资组合风险
        
        Args:
            nav_dict: dict, {fund_name: nav_series}
            portfolio_weights: dict, {fund_name: weight} 权重，None则等权
        
        Returns:
            dict: 组合分析 + 各基金分析 + 相关性矩阵
        """
        # 各基金分析
        fund_results = {}
        for name, navs in nav_dict.items():
            fund_results[name] = self.analyze_single_fund(navs, name)
        
        # 相关性矩阵
        corr_matrix = self.calculate_correlation_matrix(nav_dict)
        
        # 组合净值（加权）
        # 对齐长度
        min_len = min(len(v) for v in nav_dict.values())
        aligned_navs = {k: v[-min_len:] for k, v in nav_dict.items()}
        
        # 归一化后加权
        if portfolio_weights is None:
            weights = {k: 1.0 / len(nav_dict) for k in nav_dict}
        else:
            weights = portfolio_weights
        
        # 标准化到同一起点
        normalized = {}
        for k, navs in aligned_navs.items():
            normalized[k] = np.array(navs) / navs[0]
        
        portfolio_nav = np.zeros(min_len)
        for k in normalized:
            w = weights.get(k, 1.0 / len(nav_dict))
            portfolio_nav += w * normalized[k]
        
        portfolio_analysis = self.analyze_single_fund(portfolio_nav, "组合")
        
        return {
            "portfolio": portfolio_analysis,
            "funds": fund_results,
            "correlation_matrix": corr_matrix.to_dict() if not corr_matrix.empty else {},
            "weights": weights,
        }


if __name__ == "__main__":
    # 测试
    np.random.seed(42)
    n = 252
    
    # 生成3只基金模拟数据
    funds = {}
    for name in ["沪深300ETF", "中证500ETF", "纳斯达克ETF"]:
        base = 1.0
        returns = np.random.normal(0.0003, 0.012, n)
        if name == "纳斯达克ETF":
            returns = np.random.normal(0.0005, 0.015, n)
        navs = base * np.exp(np.cumsum(returns))
        funds[name] = navs
    
    analyzer = FundRiskAnalyzer(risk_free_rate=0.025)
    
    # 单基金分析
    print("=== 单基金风险分析 ===")
    for name, navs in funds.items():
        r = analyzer.analyze_single_fund(navs, name)
        print(f"\n{r['fund_name']}:")
        print(f"  年化收益: {r['annualized_return_pct']}%")
        print(f"  年化波动: {r['annualized_volatility_pct']}%")
        print(f"  最大回撤: {r['max_drawdown']['max_drawdown_pct']}%")
        print(f"  夏普比率: {r['sharpe_ratio']}")
        print(f"  卡玛比率: {r['calmar_ratio']}")
    
    # 组合分析
    print("\n=== 组合风险分析 ===")
    weights = {"沪深300ETF": 0.4, "中证500ETF": 0.3, "纳斯达克ETF": 0.3}
    portfolio = analyzer.analyze_portfolio(funds, weights)
    print(f"组合年化收益: {portfolio['portfolio']['annualized_return_pct']}%")
    print(f"组合最大回撤: {portfolio['portfolio']['max_drawdown']['max_drawdown_pct']}%")
    print(f"组合夏普比率: {portfolio['portfolio']['sharpe_ratio']}")
    print(f"\n相关性矩阵:")
    print(pd.DataFrame(portfolio['correlation_matrix']))
