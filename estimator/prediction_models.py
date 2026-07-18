# -*- coding: utf-8 -*-
"""预测模型模块"""
import numpy as np
import pandas as pd
from datetime import datetime, timedelta


class PredictionModels:
    """基金净值预测模型集合"""
    
    @staticmethod
    def moving_average(navs, window=5):
        """简单移动平均预测"""
        if len(navs) < window:
            return None
        return np.mean(navs[-window:])
    
    @staticmethod
    def exponential_moving_average(navs, span=5):
        """指数移动平均"""
        if len(navs) < 2:
            return None
        alpha = 2 / (span + 1)
        ema = navs[0]
        for val in navs[1:]:
            ema = alpha * val + (1 - alpha) * ema
        return ema
    
    @staticmethod
    def linear_regression(navs, predict_ahead=1):
        """线性回归预测"""
        x = np.arange(len(navs))
        A = np.vstack([x, np.ones(len(navs))]).T
        slope, intercept = np.linalg.lstsq(A, navs, rcond=None)[0]
        next_x = len(navs) + predict_ahead - 1
        return slope * next_x + intercept
    
    @staticmethod
    def monte_carlo_simulation(navs, days=30, simulations=1000):
        """蒙特卡洛模拟预测未来净值路径
        
        Returns:
            dict: {mean_path, ci_lower, ci_upper, prob_up}
        """
        if len(navs) < 10:
            return {}
        
        returns = np.diff(navs) / navs[:-1]
        mu = np.mean(returns)
        sigma = np.std(returns)
        last_nav = navs[-1]
        
        dt = 1  # 1天
        paths = np.zeros((simulations, days))
        
        for i in range(simulations):
            path = [last_nav]
            for d in range(days):
                # 几何布朗运动
                shock = np.random.normal(mu, sigma)
                next_nav = path[-1] * (1 + shock)
                path.append(next_nav)
            paths[i] = path[1:]
        
        mean_path = np.mean(paths, axis=0)
        ci_lower = np.percentile(paths, 5, axis=0)
        ci_upper = np.percentile(paths, 95, axis=0)
        
        # 上涨概率
        prob_up = np.mean(paths[:, -1] > last_nav) * 100
        
        return {
            "mean_path": mean_path.tolist(),
            "ci_lower": ci_lower.tolist(),
            "ci_upper": ci_upper.tolist(),
            "prob_up": round(prob_up, 2),
            "last_nav": last_nav,
            "expected_nav": round(mean_path[-1], 4),
            "expected_return_pct": round((mean_path[-1] - last_nav) / last_nav * 100, 4) if last_nav != 0 else 0,
        }
    
    @staticmethod
    def bollinger_bands(navs, window=20, num_std=2):
        """布林带分析"""
        if len(navs) < window:
            return {}
        
        ma = np.mean(navs[-window:])
        std = np.std(navs[-window:])
        upper = ma + num_std * std
        lower = ma - num_std * std
        
        current = navs[-1]
        position = (current - lower) / (upper - lower) if (upper - lower) != 0 else 0.5
        
        signal = "hold"
        if position > 0.9:
            signal = "overbought"
        elif position < 0.1:
            signal = "oversold"
        elif position > 0.6 and position <= 0.9:
            signal = "caution"
        elif position < 0.4 and position >= 0.1:
            signal = "opportunity"
        
        return {
            "middle_band": round(ma, 4),
            "upper_band": round(upper, 4),
            "lower_band": round(lower, 4),
            "current_position": round(position, 4),
            "signal": signal,
        }
    
    @staticmethod
    def multi_model_ensemble(navs, weights=None):
        """多模型集成预测"""
        if weights is None:
            weights = {"ma": 0.3, "ema": 0.3, "lr": 0.4}
        
        predictions = {}
        if len(navs) >= 5:
            predictions["ma"] = PredictionModels.moving_average(navs, window=5)
        if len(navs) >= 5:
            predictions["ema"] = PredictionModels.exponential_moving_average(navs, span=5)
        if len(navs) >= 10:
            predictions["lr"] = PredictionModels.linear_regression(navs, predict_ahead=1)
        
        ensemble = 0
        total_w = 0
        for model, pred in predictions.items():
            if pred is not None and model in weights:
                ensemble += pred * weights[model]
                total_w += weights[model]
        
        if total_w > 0:
            ensemble /= total_w
        
        return {
            "individual": {k: round(v, 4) for k, v in predictions.items()},
            "ensemble": round(ensemble, 4) if total_w > 0 else None,
            "last_nav": round(navs[-1], 4) if len(navs) > 0 else None,
            "expected_change_pct": round((ensemble - navs[-1]) / navs[-1] * 100, 4) if total_w > 0 and len(navs) > 0 else 0,
        }


if __name__ == "__main__":
    import numpy as np
    np.random.seed(42)
    navs = 1.0 * np.exp(np.cumsum(np.random.normal(0.0002, 0.008, 60)))
    
    print("=== 多模型集成预测 ===")
    r = PredictionModels.multi_model_ensemble(navs)
    print(r)
    
    print("\n=== 蒙特卡洛模拟 ===")
    mc = PredictionModels.monte_carlo_simulation(navs, days=30, simulations=500)
    print(f"上涨概率: {mc['prob_up']}%")
    print(f"预期净值: {mc['expected_nav']}")
    
    print("\n=== 布林带分析 ===")
    bb = PredictionModels.bollinger_bands(navs)
    print(bb)
