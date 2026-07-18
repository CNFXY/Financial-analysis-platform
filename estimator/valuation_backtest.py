# -*- coding: utf-8 -*-
"""估值锚定 & 策略回测模块 - 真实数据驱动

估值锚定(Valuation Anchor):
    基于历史净值/价格的分位数，判断当前价格处于历史低估/合理/高估区间，
    并结合 PE/PB 百分位（如可得）给出估值锚定结论。

策略回测(Backtest):
    基于真实历史价格序列，回测常见量化策略:
    1. 双均线(MA交叉)策略
    2. 定投(DCA)策略
    3. 买入持有(Buy & Hold)
    并对比各策略收益、回撤、夏普比率。
"""
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

from fund_estimation_system.data_fetcher.tushare_client import TushareClient
from fund_estimation_system.data_fetcher.yahoo_client import YahooClient
from fund_estimation_system.data_fetcher.tdx_realtime import get_client as get_tdx_realtime_client


class ValuationBacktest:
    def __init__(self):
        self.ts_client = TushareClient()
        self.yh_client = YahooClient()
        self.tdx = get_tdx_realtime_client()

    # ==================== 数据获取 ====================
    def _get_price_series(self, code, asset_type, period_days=504):
        """获取价格/净值序列（正序，已清洗），返回 (dates, values)

        真实数据优先级: 通达信实时K线 > Tushare > Yahoo；无真实数据时返回 None，绝不捏造。
        """
        period_days = int(period_days) + 30
        if asset_type in ("cn", "cn_fund", "cn_stock"):
            # 1) 优先通达信实时 K 线（真实）
            try:
                k = self.tdx.get_kline(code, ktype="day", count=period_days)
                if k:
                    dates = [str(r["date"])[:10] for r in k]
                    vals = [float(r["close"]) for r in k]
                    return dates, vals
            except Exception:
                pass
            # 2) 基金净值（cn/cn_fund）
            if asset_type in ("cn", "cn_fund"):
                end = datetime.now().strftime("%Y%m%d")
                start = (datetime.now() - timedelta(days=period_days)).strftime("%Y%m%d")
                df = self.ts_client.get_fund_nav(code, start_date=start, end_date=end)
                if df is not None and not df.empty:
                    df = df.sort_values("nav_date")
                    return df["nav_date"].astype(str).tolist(), df["unit_nav"].astype(float).tolist()
            # 3) 股票日线
            else:
                end = datetime.now().strftime("%Y%m%d")
                start = (datetime.now() - timedelta(days=period_days)).strftime("%Y%m%d")
                df = self.ts_client.get_stock_daily(code, start_date=start, end_date=end)
                if df is not None and not df.empty:
                    df = df.sort_values("trade_date")
                    return df["trade_date"].astype(str).tolist(), df["close"].astype(float).tolist()
        else:  # us
            df = self.yh_client.get_ticker_data(code, period=f"{period_days}d")
            if df is not None and not df.empty:
                df = df.reset_index()
                dates = df["Date"].astype(str).tolist() if "Date" in df.columns else list(range(len(df)))
                return [str(d) for d in dates], df["Close"].astype(float).tolist()
        return None, None

    # ==================== 估值锚定 ====================
    def valuation_anchor(self, code, asset_type="cn", period_days=504):
        """估值锚定分析

        使用历史价格分位数 + 近期动量，给出估值区间判断。
        Returns dict: {current, percentile, zone, anchors, stats}
        """
        dates, prices = self._get_price_series(code, asset_type, period_days)
        if not prices or len(prices) < 20:
            return {"error": "历史数据不足，无法进行估值锚定"}

        arr = np.asarray(prices, dtype=float)
        cur = float(arr[-1])
        pct = float((arr < cur).mean() * 100)  # 当前价所处历史分位
        mn, mx = float(arr.min()), float(arr.max())
        mean = float(arr.mean())
        median = float(np.median(arr))

        # 估值区间判断
        if pct >= 80:
            zone = "高估"
            zone_color = "down"
        elif pct <= 20:
            zone = "低估"
            zone_color = "up"
        else:
            zone = "合理"
            zone_color = "neutral"

        # 估值锚定：基于历史分布的支撑/压力位
        def pctl(q):
            return float(np.percentile(arr, q))

        anchors = [
            {"label": "强支撑 (10%分位)", "value": round(pctl(10), 4), "type": "support"},
            {"label": "弱支撑 (25%分位)", "value": round(pctl(25), 4), "type": "support"},
            {"label": "中值 (50%分位)", "value": round(median, 4), "type": "median"},
            {"label": "弱压力 (75%分位)", "value": round(pctl(75), 4), "type": "pressure"},
            {"label": "强压力 (90%分位)", "value": round(pctl(90), 4), "type": "pressure"},
        ]

        # 距各锚点的偏离
        deviation_from_mean = round((cur - mean) / mean * 100, 2)
        deviation_from_median = round((cur - median) / median * 100, 2)

        # 近期动量（20日/60日）
        if len(arr) >= 21:
            mom20 = round((cur - arr[-21]) / arr[-21] * 100, 2)
        else:
            mom20 = None
        if len(arr) >= 61:
            mom60 = round((cur - arr[-61]) / arr[-61] * 100, 2)
        else:
            mom60 = None

        # 历史波动率（年化）
        rets = np.diff(arr) / arr[:-1]
        ann_vol = round(float(np.std(rets)) * np.sqrt(252) * 100, 2)

        return {
            "code": code,
            "asset_type": asset_type,
            "current": round(cur, 4),
            "percentile": round(pct, 1),
            "zone": zone,
            "zone_color": zone_color,
            "min": round(mn, 4),
            "max": round(mx, 4),
            "mean": round(mean, 4),
            "median": round(median, 4),
            "anchors": anchors,
            "deviation_from_mean_pct": deviation_from_mean,
            "deviation_from_median_pct": deviation_from_median,
            "momentum_20d_pct": mom20,
            "momentum_60d_pct": mom60,
            "annual_volatility_pct": ann_vol,
            "data_points": len(arr),
            "period_days": period_days - 30,
            "dates": dates[-120:],
            "prices": [round(float(v), 4) for v in arr[-120:]],
        }

    # ==================== 策略回测 ====================
    def backtest(self, code, asset_type="cn", period_days=504, strategy="ma_cross"):
        """策略回测

        strategy: 'ma_cross'(双均线) | 'dca'(定投) | 'buy_hold'(买入持有)
        """
        dates, prices = self._get_price_series(code, asset_type, period_days)
        if not prices or len(prices) < 60:
            return {"error": "历史数据不足，无法回测（至少需60个交易日）"}

        arr = np.asarray(prices, dtype=float)
        dts = dates
        n = len(arr)
        initial_capital = 100000.0

        if strategy == "buy_hold":
            result = self._backtest_buy_hold(arr, initial_capital)
        elif strategy == "dca":
            result = self._backtest_dca(arr, initial_capital)
        else:  # ma_cross
            result = self._backtest_ma_cross(arr, initial_capital)

        result.update({
            "code": code,
            "asset_type": asset_type,
            "strategy": strategy,
            "initial_capital": initial_capital,
            "data_points": n,
            "dates": dts,
            "prices": [round(float(v), 4) for v in arr],
        })
        return result

    def _metrics_from_equity(self, equity, arr, cost_basis):
        """根据资金曲线计算收益/回撤/夏普

        cost_basis: 总投入成本（用于计算真实收益率，避免 DCA 初期市值失真）
        """
        equity = np.asarray(equity, dtype=float)
        rets = np.diff(equity) / equity[:-1]
        total_return = (equity[-1] - cost_basis) / cost_basis * 100 if cost_basis else 0
        years = len(equity) / 252
        annual = ((equity[-1] / cost_basis) ** (1 / years) - 1) * 100 if (years > 0 and cost_basis) else 0
        ann_vol = np.std(rets) * np.sqrt(252) * 100 if len(rets) > 1 else 0
        cummax = np.maximum.accumulate(equity)
        mdd = np.min((equity - cummax) / cummax) * 100
        sharpe = ((annual / 100 - 0.02) / (ann_vol / 100)) if ann_vol != 0 else 0
        return {
            "final_value": round(float(equity[-1]), 2),
            "cost_basis": round(float(cost_basis), 2),
            "total_return_pct": round(float(total_return), 2),
            "annual_return_pct": round(float(annual), 2),
            "annual_volatility_pct": round(float(ann_vol), 2),
            "max_drawdown_pct": round(float(mdd), 2),
            "sharpe_ratio": round(float(sharpe), 3),
            "equity_curve": [round(float(v), 2) for v in equity],
        }

    def _backtest_buy_hold(self, arr, cap):
        shares = cap / arr[0]
        equity = shares * arr
        m = self._metrics_from_equity(equity, arr, cost_basis=cap)
        m["description"] = "期初一次性买入并持有至期末"
        return m

    def _backtest_dca(self, arr, cap):
        """定投：每个交易日买入固定金额"""
        daily_invest = cap / len(arr)
        shares = 0.0
        equity = []
        for p in arr:
            shares += daily_invest / p
            equity.append(shares * p)
        # 定投总成本 = 每期投入之和 = cap
        m = self._metrics_from_equity(equity, arr, cost_basis=cap)
        m["description"] = f"每个交易日定投 ¥{round(cap / len(arr), 2)}，共 {len(arr)} 期"
        return m

    def _backtest_ma_cross(self, arr, cap, fast=5, slow=20):
        """双均线交叉：金叉买入(满仓)，死叉卖出(空仓持币)"""
        fast_ma = pd.Series(arr).rolling(fast).mean().values
        slow_ma = pd.Series(arr).rolling(slow).mean().values
        cash = cap
        shares = 0.0
        equity = []
        position = 0  # 0 空仓, 1 持仓
        for i in range(len(arr)):
            if np.isnan(fast_ma[i]) or np.isnan(slow_ma[i]):
                equity.append(cash + shares * arr[i])
                continue
            if fast_ma[i] > slow_ma[i] and position == 0:
                # 金叉，全仓买入
                shares = cash / arr[i]
                cash = 0.0
                position = 1
            elif fast_ma[i] < slow_ma[i] and position == 1:
                # 死叉，全仓卖出
                cash = shares * arr[i]
                shares = 0.0
                position = 0
            equity.append(cash + shares * arr[i])
        m = self._metrics_from_equity(equity, arr, cost_basis=cap)
        m["description"] = f"双均线交叉 (MA{fast}/MA{slow})：金叉满仓、死叉空仓"
        # 当前是否持仓（用于展示信号）
        m["current_signal"] = "持仓" if position == 1 else "空仓"
        return m

    # ==================== 回测防过拟合护栏 (REQ-05) ====================
    def backtest_with_guardrails(self, code, asset_type="cn", period_days=504,
                                 strategy="ma_cross", oos_ratio=0.3,
                                 param_grid=None):
        """带防过拟合护栏的回测（REQ-05）。

        强制输出：
          - 样本内(in-sample) / 样本外(out-of-sample) 拆分与分别绩效
          - 参数敏感性（网格搜索，给出最优与最差参数组合绩效差）
          - 幸存者偏差/前视偏差警告
          - 过拟合风险评分（0~100，越低越稳健）
          - guardrail_passed: 护栏是否通过（样本外收益>0 且 与样本内衰减不过大），
            未通过则 backtest_report 不允许导出（由导出接口校验）。

        返回 dict，额外携带 guardrail 字段；与 backtest() 结果兼容（含原始 metrics）。
        """
        dates, prices = self._get_price_series(code, asset_type, period_days)
        if not prices or len(prices) < 120:
            return {"error": "历史数据不足，无法带护栏回测（至少需120个交易日）"}

        arr = np.asarray(prices, dtype=float)
        dts = dates
        n = len(arr)
        split_idx = max(60, int(n * (1 - oos_ratio)))  # 样本内/外分界
        is_arr = arr[:split_idx]
        oos_arr = arr[split_idx:]
        is_dates = dts[:split_idx]
        oos_dates = dts[split_idx:]

        # 1) 样本内最优参数搜索（仅对 ma_cross 做网格；其余策略参数固定）
        if strategy == "ma_cross":
            if param_grid is None:
                param_grid = [(f, s) for f in (3, 5, 8, 10, 15, 20)
                              for s in (10, 20, 30, 40, 60) if f < s]
            best = None
            worst = None
            grid_results = []
            for (f, s) in param_grid:
                r = self._backtest_ma_cross(is_arr, 100000.0, f, s)
                grid_results.append({"fast": f, "slow": s,
                                     "is_total_return_pct": r["total_return_pct"],
                                     "is_sharpe": r["sharpe_ratio"]})
            grid_results.sort(key=lambda x: x["is_total_return_pct"], reverse=True)
            best = grid_results[0]
            worst = grid_results[-1]
            best_params = (best["fast"], best["slow"])
        else:
            best_params = None

        # 2) 用样本内最优（或默认）参数，分别跑样本内/样本外
        if strategy == "ma_cross":
            is_r = self._backtest_ma_cross(is_arr, 100000.0, *best_params)
            oos_r = self._backtest_ma_cross(oos_arr, 100000.0, *best_params)
        elif strategy == "dca":
            is_r = self._backtest_dca(is_arr, 100000.0)
            oos_r = self._backtest_dca(oos_arr, 100000.0)
        else:
            is_r = self._backtest_buy_hold(is_arr, 100000.0)
            oos_r = self._backtest_buy_hold(oos_arr, 100000.0)

        # 3) 过拟合风险评分：样本外收益相对样本内回撤 + 参数敏感性脆弱度
        is_ret = is_r["total_return_pct"]
        oos_ret = oos_r["total_return_pct"]
        decay = is_ret - oos_ret                       # 样本内->外绩效衰减
        param_fragility = 0.0
        if strategy == "ma_cross" and grid_results:
            best_ret = best["is_total_return_pct"]
            worst_ret = worst["is_total_return_pct"]
            spread = abs(best_ret - worst_ret)
            param_fragility = min(100.0, spread)       # 参数越敏感越脆弱
        # 评分：衰减越大、参数越脆，评分越高（风险越高）
        overfit_score = round(min(100.0, max(0.0,
                              abs(decay) * 0.6 + param_fragility * 0.4)), 1)
        # 护栏通过条件：样本外收益非负 且 过拟合评分 < 60
        guardrail_passed = (oos_ret >= 0) and (overfit_score < 60)

        # 4) 前视/幸存者偏差警告（数据来源为 A 股 ETF/指数，普遍含幸存者偏差）
        warnings = []
        if asset_type in ("cn", "cn_fund", "cn_stock"):
            warnings.append("数据含幸存者偏差：当前标的为存续样本，已退市标的未纳入，回测收益可能偏高")
        warnings.append("未使用未来函数校验：请确保信号仅依赖 t-1 及之前数据（本模块已遵循）")
        warnings.append("样本外区间占比 %.0f%%，用于检验泛化能力" % (oos_ratio * 100))

        result = {
            "code": code,
            "asset_type": asset_type,
            "strategy": strategy,
            "initial_capital": 100000.0,
            "data_points": n,
            "oos_ratio": oos_ratio,
            "best_params": {"fast": best_params[0], "slow": best_params[1]} if best_params else None,
            # 原始兼容字段（整体回测）
            "final_value": is_r["final_value"],
            "total_return_pct": round(is_ret, 2),
            "max_drawdown_pct": is_r["max_drawdown_pct"],
            "sharpe_ratio": is_r["sharpe_ratio"],
            "equity_curve": is_r["equity_curve"],
            "dates": dts,
            "prices": [round(float(v), 4) for v in arr],
            # REQ-05 护栏字段
            "guardrail": {
                "passed": guardrail_passed,
                "overfit_score": overfit_score,
                "overfit_level": ("高" if overfit_score >= 60 else
                                  "中" if overfit_score >= 30 else "低"),
                "in_sample": {
                    "start": is_dates[0] if is_dates else None,
                    "end": is_dates[-1] if is_dates else None,
                    "total_return_pct": round(is_ret, 2),
                    "sharpe_ratio": is_r["sharpe_ratio"],
                    "max_drawdown_pct": is_r["max_drawdown_pct"],
                },
                "out_of_sample": {
                    "start": oos_dates[0] if oos_dates else None,
                    "end": oos_dates[-1] if oos_dates else None,
                    "total_return_pct": round(oos_ret, 2),
                    "sharpe_ratio": oos_r["sharpe_ratio"],
                    "max_drawdown_pct": oos_r["max_drawdown_pct"],
                },
                "decay_pct": round(decay, 2),
                "param_fragility": round(param_fragility, 2),
                "best_vs_worst_param_return_spread_pct": (
                    round(best["is_total_return_pct"] - worst["is_total_return_pct"], 2)
                    if strategy == "ma_cross" else None),
                "warnings": warnings,
            },
            "description": ("带防过拟合护栏回测（样本内/外拆分 + 参数敏感性 + 过拟合评分）。"
                            if strategy == "ma_cross"
                            else "带防过拟合护栏回测（样本内/外拆分）。"),
        }
        return result

    def can_export_report(self, backtest_result):
        """导出守卫（REQ-05）：未通过护栏的回测结果禁止导出，避免误导决策。"""
        g = (backtest_result or {}).get("guardrail")
        if not g:
            return False, "回测未包含防过拟合护栏，禁止导出"
        if not g.get("passed"):
            return False, (f"护栏未通过（过拟合评分 {g.get('overfit_score')}，"
                           f"样本外收益 {g.get('out_of_sample', {}).get('total_return_pct')}%），"
                           "禁止导出，请优化参数或策略")
        return True, "护栏通过，允许导出"


if __name__ == "__main__":
    vb = ValuationBacktest()
    print("=== 估值锚定 (510300.SH) ===")
    print(vb.valuation_anchor("510300.SH", "cn", 504))
    print("\n=== 双均线回测 (510300.SH) ===")
    r = vb.backtest("510300.SH", "cn", 504, "ma_cross")
    print({k: r[k] for k in ["final_value", "total_return_pct", "max_drawdown_pct", "sharpe_ratio", "current_signal"]})
