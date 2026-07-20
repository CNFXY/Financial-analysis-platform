# -*- coding: utf-8 -*-
"""基金净值估算引擎"""
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from fund_estimation_system.data_fetcher.tushare_client import TushareClient
from fund_estimation_system.data_fetcher.yahoo_client import YahooClient
from fund_estimation_system.data_fetcher.tdx_data_reader import TdxDataReader
from fund_estimation_system.data_fetcher.tdx_realtime import TdxRealtimeClient


class FundNavEstimator:
    """基金净值估算器
    
    支持三种估算方式:
    1. 历史净值趋势外推（基于移动平均、线性回归）
    2. 持仓股票法（通过持仓股票当日涨跌估算基金净值）
    3. 指数映射法（根据基金跟踪指数估算）

    数据源优先级（全部为真实数据，无数据时如实返回 None，绝不捏造）:
    1. 通达信本地数据 (自动检测安装目录)
    2. Tushare Pro (需要 API Token)
    """

    
    def __init__(self, tushare_token=None):
        self.ts_client = TushareClient(token=tushare_token)
        self.yh_client = YahooClient()
        self.tdx_reader = TdxDataReader()
        self.tdx_realtime = TdxRealtimeClient()
    
    def _get_nav_data(self, fund_code, fund_type="cn", days=20):
        """获取净值数据，支持多数据源回退
        
        数据源优先级:
        1. 通达信本地数据 (如果安装且数据存在) - 用户明确要求真实数据
        2. Tushare Pro (需要 API Token)
        3. 模拟数据 (演示模式)
        
        Returns:
            DataFrame with 'unit_nav' column
        """
        if fund_type == "cn":
            end_date = datetime.now().strftime("%Y%m%d")
            start_date = (datetime.now() - timedelta(days=days + 30)).strftime("%Y%m%d")
            
            # 1. 优先使用通达信本地数据（用户要求真实数据）
            if self.tdx_reader.available:
                code_clean = fund_code.upper().replace('.SH', '').replace('.SZ', '').replace('.BJ', '')
                # 先获取全部数据，不过滤日期（通达信数据可能较旧）
                tdx_df = self.tdx_reader.get_stock_daily(code_clean)
                if tdx_df is not None and not tdx_df.empty:
                    # 如果有足够数据，使用日期过滤；否则使用全部数据
                    if len(tdx_df) >= days:
                        # 尝试日期过滤
                        filtered = tdx_df[tdx_df['date'] >= pd.to_datetime(start_date)]
                        if len(filtered) >= days:
                            tdx_df = filtered
                        else:
                            # 数据较旧，使用最近的数据
                            tdx_df = tdx_df.tail(days + 30)
                    tdx_df = tdx_df.rename(columns={
                        'date': 'nav_date',
                        'close': 'unit_nav',
                    })
                    tdx_df['nav_date'] = tdx_df['nav_date'].dt.strftime('%Y%m%d')
                    # 标记数据源
                    tdx_df['_source'] = 'tdx'
                    return tdx_df
            
            # 2. 尝试 Tushare Pro
            nav_df = self.ts_client.get_fund_nav(fund_code, start_date=start_date, end_date=end_date)
            if nav_df is not None and not nav_df.empty:
                return nav_df
            
            # 3. 回退到模拟数据
        else:
            nav_df = self.yh_client.get_ticker_data(fund_code, period=f"{days+30}d")
            if nav_df is not None and not nav_df.empty:
                nav_df = nav_df.reset_index()
                nav_df["unit_nav"] = nav_df["Close"]
                return nav_df
        
        return None
    
    def estimate_by_trend(self, nav_df, method="ma", days=5, predict_days=1):
        """基于历史趋势估算未来净值
        
        Args:
            nav_df: 历史净值DataFrame，需包含 unit_nav 列
            method: ma(移动平均), lr(线性回归), ema(指数移动平均)
            days: 用于计算的历史天数
            predict_days: 预测未来天数
        
        Returns:
            dict: {estimated_nav, confidence, trend}
        """
        if nav_df is None or nav_df.empty or len(nav_df) < days:
            return {"estimated_nav": None, "confidence": 0, "trend": "insufficient_data"}
        
        navs = nav_df["unit_nav"].astype(float).values[-days:]
        
        if method == "ma":
            # 简单移动平均
            weights = np.ones(days) / days
            est = np.dot(navs, weights)
            # 置信度基于历史波动率
            std = np.std(navs)
            confidence = max(0, 1 - std / np.mean(navs)) if np.mean(navs) != 0 else 0
        
        elif method == "ema":
            # 指数移动平均
            alpha = 2 / (days + 1)
            est = navs[-1] * (1 - alpha) + np.mean(navs) * alpha
            std = np.std(navs)
            confidence = max(0, 1 - std / np.mean(navs)) if np.mean(navs) != 0 else 0
        
        elif method == "lr":
            # 线性回归
            x = np.arange(len(navs))
            A = np.vstack([x, np.ones(len(navs))]).T
            slope, intercept = np.linalg.lstsq(A, navs, rcond=None)[0]
            est = slope * len(navs) + intercept
            # R²近似作为置信度
            ss_res = np.sum((navs - (slope * x + intercept)) ** 2)
            ss_tot = np.sum((navs - np.mean(navs)) ** 2)
            r2 = 1 - ss_res / ss_tot if ss_tot != 0 else 0
            confidence = max(0, r2)
        else:
            est = np.mean(navs)
            confidence = 0.5
        
        trend = "up" if est > navs[-1] else "down" if est < navs[-1] else "flat"
        
        return {
            "estimated_nav": round(est, 4),
            "confidence": round(confidence, 4),
            "trend": trend,
            "last_nav": round(navs[-1], 4),
            "predicted_change_pct": round((est - navs[-1]) / navs[-1] * 100, 4) if navs[-1] != 0 else 0,
        }
    
    def estimate_by_wma(self, nav_df, days=10, predict_days=1):
        """加权移动平均估算（近期数据权重更高）
        
        Args:
            nav_df: 历史净值DataFrame
            days: 用于计算的历史天数
            predict_days: 预测未来天数
        
        Returns:
            dict: {estimated_nav, confidence, trend}
        """
        if nav_df is None or nav_df.empty or len(nav_df) < days:
            return {"estimated_nav": None, "confidence": 0, "trend": "insufficient_data"}
        
        navs = nav_df["unit_nav"].astype(float).values[-days:]
        
        # 线性加权：越近权重越大
        weights = np.arange(1, days + 1)
        weights = weights / weights.sum()
        
        est = np.dot(navs, weights)
        
        # 计算置信度
        std = np.std(navs)
        confidence = max(0, 1 - std / np.mean(navs)) if np.mean(navs) != 0 else 0
        
        trend = "up" if est > navs[-1] else "down" if est < navs[-1] else "flat"
        
        return {
            "estimated_nav": round(est, 4),
            "confidence": round(confidence, 4),
            "trend": trend,
            "last_nav": round(navs[-1], 4),
            "predicted_change_pct": round((est - navs[-1]) / navs[-1] * 100, 4) if navs[-1] != 0 else 0,
        }
    
    def estimate_by_momentum(self, nav_df, days=20, predict_days=1):
        """动量趋势估算（基于近期涨跌幅趋势）
        
        Args:
            nav_df: 历史净值DataFrame
            days: 用于计算的历史天数
            predict_days: 预测未来天数
        
        Returns:
            dict: {estimated_nav, confidence, trend}
        """
        if nav_df is None or nav_df.empty or len(nav_df) < days:
            return {"estimated_nav": None, "confidence": 0, "trend": "insufficient_data"}
        
        navs = nav_df["unit_nav"].astype(float).values[-days:]
        
        # 计算每日收益率
        returns = np.diff(navs) / navs[:-1]
        
        # 计算动量（近期收益率的加权平均）
        momentum_weights = np.exp(np.linspace(0, 1, len(returns)))
        momentum_weights = momentum_weights / momentum_weights.sum()
        momentum = np.dot(returns, momentum_weights)
        
        # 基于动量预测
        est = navs[-1] * (1 + momentum * predict_days)
        
        # 置信度基于动量的稳定性
        return_std = np.std(returns)
        confidence = max(0, 1 - return_std / (abs(momentum) + 1e-8)) if abs(momentum) > 1e-8 else 0.5
        
        trend = "up" if momentum > 0 else "down" if momentum < 0 else "flat"
        
        return {
            "estimated_nav": round(est, 4),
            "confidence": round(confidence, 4),
            "trend": trend,
            "last_nav": round(navs[-1], 4),
            "momentum": round(momentum * 100, 4),
            "predicted_change_pct": round((est - navs[-1]) / navs[-1] * 100, 4) if navs[-1] != 0 else 0,
        }
    
    def estimate_by_volatility_adjusted(self, nav_df, days=30, predict_days=1):
        """波动率调整估算（考虑波动率的均值回归）
        
        Args:
            nav_df: 历史净值DataFrame
            days: 用于计算的历史天数
            predict_days: 预测未来天数
        
        Returns:
            dict: {estimated_nav, confidence, trend}
        """
        if nav_df is None or nav_df.empty or len(nav_df) < days:
            return {"estimated_nav": None, "confidence": 0, "trend": "insufficient_data"}
        
        navs = nav_df["unit_nav"].astype(float).values[-days:]
        
        # 计算均值和标准差
        mean_nav = np.mean(navs)
        std_nav = np.std(navs)
        
        # 当前价格偏离均值的程度（z-score）
        z_score = (navs[-1] - mean_nav) / std_nav if std_nav > 0 else 0
        
        # 均值回归强度：偏离越多，回归越强
        reversion_strength = 0.1  # 回归系数
        expected_change = -z_score * reversion_strength * std_nav / mean_nav
        
        # 叠加趋势
        recent_trend = (navs[-1] - navs[-5]) / navs[-5] if len(navs) >= 5 else 0
        
        # 综合预测
        total_change = expected_change + recent_trend * 0.3
        est = navs[-1] * (1 + total_change * predict_days)
        
        # 置信度基于波动率的稳定性
        confidence = max(0, 1 - std_nav / mean_nav) if mean_nav != 0 else 0.5
        
        trend = "up" if total_change > 0 else "down" if total_change < 0 else "flat"
        
        return {
            "estimated_nav": round(est, 4),
            "confidence": round(confidence, 4),
            "trend": trend,
            "last_nav": round(navs[-1], 4),
            "z_score": round(z_score, 4),
            "predicted_change_pct": round((est - navs[-1]) / navs[-1] * 100, 4) if navs[-1] != 0 else 0,
        }
    
    def estimate_ensemble(self, nav_df, days=30, predict_days=1):
        """多模型融合估算（集成学习）
        
        综合多个模型的预测结果，按置信度加权
        
        Args:
            nav_df: 历史净值DataFrame
            days: 用于计算的历史天数
            predict_days: 预测未来天数
        
        Returns:
            dict: {estimated_nav, confidence, trend, models}
        """
        models = {}
        
        # 运行各个模型
        models["lr"] = self.estimate_by_trend(nav_df, method="lr", days=min(days, 20), predict_days=predict_days)
        models["ema"] = self.estimate_by_trend(nav_df, method="ema", days=min(days, 15), predict_days=predict_days)
        models["wma"] = self.estimate_by_wma(nav_df, days=min(days, 10), predict_days=predict_days)
        models["momentum"] = self.estimate_by_momentum(nav_df, days=min(days, 20), predict_days=predict_days)
        models["volatility"] = self.estimate_by_volatility_adjusted(nav_df, days=min(days, 30), predict_days=predict_days)
        
        # 按置信度加权融合
        total_weight = 0
        weighted_est = 0
        weighted_change = 0
        
        for name, result in models.items():
            if result.get("estimated_nav") is not None:
                weight = result.get("confidence", 0.5)
                # 不同模型赋予不同的基础权重
                base_weights = {
                    "lr": 1.2,
                    "ema": 1.0,
                    "wma": 0.9,
                    "momentum": 1.1,
                    "volatility": 0.8
                }
                weight *= base_weights.get(name, 1.0)
                
                weighted_est += result["estimated_nav"] * weight
                weighted_change += result.get("predicted_change_pct", 0) * weight
                total_weight += weight
        
        if total_weight > 0:
            final_est = weighted_est / total_weight
            final_change = weighted_change / total_weight
        else:
            final_est = models["lr"].get("estimated_nav", 0)
            final_change = models["lr"].get("predicted_change_pct", 0)
        
        # 综合置信度
        avg_confidence = np.mean([m.get("confidence", 0) for m in models.values()])
        # 模型一致性作为额外置信度加分
        changes = [m.get("predicted_change_pct", 0) for m in models.values()]
        agreement = 1 - np.std(changes) / (np.mean(np.abs(changes)) + 1e-8)
        final_confidence = min(1, avg_confidence * 0.7 + max(0, agreement) * 0.3)
        
        trend = "up" if final_change > 0 else "down" if final_change < 0 else "flat"
        
        return {
            "estimated_nav": round(final_est, 4),
            "confidence": round(final_confidence, 4),
            "trend": trend,
            "last_nav": round(models["lr"].get("last_nav", final_est), 4),
            "predicted_change_pct": round(final_change, 4),
            "model_count": len(models),
            "models": models
        }
    
    def estimate_by_holdings(self, fund_code, stock_changes):
        """基于持仓股票估算基金净值变动
        
        Args:
            fund_code: 基金代码
            stock_changes: dict, {stock_code: pct_change}
                如 {"000001.SZ": 2.5, "000002.SZ": -1.2}
        
        Returns:
            dict: {estimated_nav_change_pct, breakdown}
        """
        portfolio = self.ts_client.get_fund_portfolio(fund_code)
        if portfolio is None or portfolio.empty:
            return {"estimated_nav_change_pct": 0, "breakdown": []}
        
        total_contribution = 0
        breakdown = []
        
        for _, row in portfolio.iterrows():
            symbol = row.get("symbol", "")
            ratio = float(row.get("stk_mkv_ratio", 0)) / 100  # 转为小数
            
            if symbol in stock_changes:
                change = stock_changes[symbol] / 100
                contribution = ratio * change
                total_contribution += contribution
                breakdown.append({
                    "symbol": symbol,
                    "ratio": round(ratio * 100, 2),
                    "stock_change_pct": stock_changes[symbol],
                    "contribution": round(contribution * 100, 4),
                })
        
        return {
            "estimated_nav_change_pct": round(total_contribution * 100, 4),
            "breakdown": breakdown,
        }

    def estimate_by_realtime(self, fund_code, fund_type="cn"):
        """基于通达信实时行情估算当日涨跌（无 Tushare 权限/无历史净值时的真实数据回退）

        对场内 ETF/LOF 及部分场外指数基金，pytdx 直连行情服务器可返回真实盘中
        价与昨收，用 (price - last_close) / last_close 计算真实当日涨跌幅。
        全部为真实数据，取不到时如实返回 available=False，绝不捏造。
        """
        code = (fund_code or "").upper()
        for suf in (".SH", ".SZ", ".OF", ".BJ"):
            code = code.replace(suf, "")
        try:
            q = self.tdx_realtime.get_single_quote(code)
        except Exception:
            return {"available": False, "source": "tdx_realtime"}
        if not q or not q.get("price"):
            return {"available": False, "source": "tdx_realtime"}
        try:
            price = float(q.get("price") or 0)
            last = float(q.get("last_close") or 0)
        except (TypeError, ValueError):
            return {"available": False, "source": "tdx_realtime"}
        if last and last > 0:
            change_pct = (price - last) / last * 100
        else:
            change_pct = 0.0
        trend = "up" if change_pct > 0 else "down" if change_pct < 0 else "flat"
        return {
            "available": True,
            "realtime": True,
            "source": "tdx_realtime",
            "name": q.get("name"),
            "estimated_nav": round(price, 4),
            "last_nav": round(last, 4),
            "change_pct": round(change_pct, 4),
            "confidence": 0.6,
            "trend": trend,
        }

    def estimate_fund(self, fund_code, fund_type="cn", method="ma", 
                     stock_changes=None, days=20):
        """综合估算基金净值
        
        Args:
            fund_code: 基金代码（CN: 510300.SH, US: SPY）
            fund_type: cn(中国公募), us(海外基金)
            method: 趋势方法
            stock_changes: 用于持仓法的股票涨跌幅
            days: 历史天数
        
        Returns:
            dict: 估算结果
        """
        result = {
            "fund_code": fund_code,
            "fund_type": fund_type,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "methods": {}
        }
        
        # 1. 获取历史净值
        if fund_type == "cn":
            end_date = datetime.now().strftime("%Y%m%d")
            start_date = (datetime.now() - timedelta(days=days + 30)).strftime("%Y%m%d")
            nav_df = self._get_nav_data(fund_code, fund_type=fund_type, days=days)
        else:
            nav_df = self.yh_client.get_ticker_data(fund_code, period=f"{days+30}d")
            if nav_df is not None and not nav_df.empty:
                nav_df = nav_df.reset_index()
                nav_df["unit_nav"] = nav_df["Close"]
        
        # 2. 趋势估算
        if method == "ensemble":
            # 多模型融合
            trend_result = self.estimate_ensemble(nav_df, days=min(days, 30))
        elif method == "wma":
            # 加权移动平均
            trend_result = self.estimate_by_wma(nav_df, days=min(days, 10))
        elif method == "momentum":
            # 动量趋势
            trend_result = self.estimate_by_momentum(nav_df, days=min(days, 20))
        elif method == "volatility":
            # 波动率调整
            trend_result = self.estimate_by_volatility_adjusted(nav_df, days=min(days, 30))
        else:
            # 传统方法: ma, lr, ema
            trend_result = self.estimate_by_trend(nav_df, method=method, days=min(days, 20))
        
        result["methods"]["trend"] = trend_result

        # 2.5 实时行情回退：无历史净值（本地无数据 / Tushare 权限不足）时，
        # 用通达信实时行情给出真实盘中涨跌估算（全部为真实数据，不捏造）
        if trend_result.get("estimated_nav") is None:
            rt = self.estimate_by_realtime(fund_code, fund_type=fund_type)
            if rt.get("available"):
                result["methods"]["realtime"] = rt
                result["combined_change_pct"] = rt["change_pct"]
                result["estimated_nav"] = rt["estimated_nav"]
                result["is_realtime"] = True
                result["methods"]["trend"].update({
                    "estimated_nav": rt["estimated_nav"],
                    "last_nav": rt["last_nav"],
                    "trend": rt["trend"],
                    "confidence": rt["confidence"],
                    "change_pct": rt["change_pct"],
                })
                return result

        # 3. 持仓法估算（仅CN基金）
        if fund_type == "cn" and stock_changes:
            holding_result = self.estimate_by_holdings(fund_code, stock_changes)
            result["methods"]["holdings"] = holding_result
        
        # 4. 综合估算（加权平均）
        weights = {"trend": 0.6}
        if "holdings" in result["methods"] and result["methods"]["holdings"].get("estimated_nav_change_pct") != 0:
            weights = {"trend": 0.4, "holdings": 0.6}
        
        combined_change = 0
        total_weight = 0
        for method_name, weight in weights.items():
            if method_name == "trend" and result["methods"]["trend"]["estimated_nav"] is not None:
                last_nav = result["methods"]["trend"]["last_nav"]
                est_nav = result["methods"]["trend"]["estimated_nav"]
                change = (est_nav - last_nav) / last_nav if last_nav != 0 else 0
                combined_change += change * weight
                total_weight += weight
            elif method_name == "holdings":
                change = result["methods"]["holdings"]["estimated_nav_change_pct"] / 100
                combined_change += change * weight
                total_weight += weight
        
        if total_weight > 0:
            result["combined_change_pct"] = round(combined_change / total_weight * 100, 4)
            if "last_nav" in result["methods"]["trend"]:
                result["estimated_nav"] = round(
                    result["methods"]["trend"]["last_nav"] * (1 + result["combined_change_pct"] / 100), 4
                )
        else:
            result["combined_change_pct"] = 0
            result["estimated_nav"] = result["methods"]["trend"].get("last_nav")
        
        return result


if __name__ == "__main__":
    estimator = FundNavEstimator()
    
    # 估算中国基金
    print("=== 沪深300ETF 净值估算 ===")
    r = estimator.estimate_fund("510300.SH", fund_type="cn", method="lr", days=20)
    print(f"基金代码: {r['fund_code']}")
    print(f"最新净值: {r['methods']['trend']['last_nav']}")
    print(f"估算净值: {r['estimated_nav']}")
    print(f"估算变动: {r['combined_change_pct']}%")
    print(f"置信度: {r['methods']['trend']['confidence']}")
    print(f"趋势: {r['methods']['trend']['trend']}")
    
    # 持仓法估算
    print("\n=== 持仓法估算 ===")
    stock_changes = {"000001.SZ": 2.5, "000002.SZ": -1.2, "600000.SH": 0.8}
    r2 = estimator.estimate_fund("001753.OF", fund_type="cn", stock_changes=stock_changes)
    print(f"持仓估算变动: {r2['methods']['holdings']['estimated_nav_change_pct']}%")
    
    # 估算美股基金
    print("\n=== SPY 净值估算 ===")
    r3 = estimator.estimate_fund("SPY", fund_type="us", method="ema", days=20)
    print(f"最新价格: {r3['methods']['trend']['last_nav']}")
    print(f"估算价格: {r3['estimated_nav']}")
    print(f"估算变动: {r3['combined_change_pct']}%")
