# -*- coding: utf-8 -*-
"""定时报告生成模块"""
import os
import json
import pandas as pd
from datetime import datetime, timedelta

from fund_estimation_system import config
from fund_estimation_system.data_fetcher.tushare_client import TushareClient
from fund_estimation_system.data_fetcher.yahoo_client import YahooClient
from fund_estimation_system.data_fetcher.manual_input import ManualPortfolio
from fund_estimation_system.estimator.fund_nav_estimator import FundNavEstimator
from fund_estimation_system.estimator.portfolio_calculator import PortfolioCalculator
from fund_estimation_system.estimator.prediction_models import PredictionModels
from fund_estimation_system.estimator.tech_indicators import TechnicalIndicators
from fund_estimation_system.estimator.risk_analyzer import FundRiskAnalyzer

REPORT_DIR = config.REPORT_DIR
CACHE_DIR = config.CACHE_DIR


class ReportGenerator:
    """报告生成器 - 生成HTML/JSON格式的基金估算报告"""
    
    def __init__(self, tushare_token=None):
        self.ts_client = TushareClient(token=tushare_token)
        self.yh_client = YahooClient()
        self.estimator = FundNavEstimator(tushare_token=tushare_token)
        self.portfolio = PortfolioCalculator(tushare_token=tushare_token)
        self.risk_analyzer = FundRiskAnalyzer()
        self.tech_indicators = TechnicalIndicators()
    
    def generate_market_overview(self, funds=None):
        """生成市场概览"""
        if funds is None:
            funds = [
                {"code": "510300.SH", "name": "沪深300ETF", "type": "cn"},
                {"code": "510500.SH", "name": "中证500ETF", "type": "cn"},
                {"code": "159915.SZ", "name": "创业板ETF", "type": "cn"},
                {"code": "SPY", "name": "S&P 500 ETF", "type": "us"},
                {"code": "QQQ", "name": "NASDAQ-100 ETF", "type": "us"},
            ]
        
        results = []
        for f in funds:
            try:
                hist = self.portfolio.calculate_historical_returns(f["code"], f["type"], period_days=90)
                est = self.estimator.estimate_fund(f["code"], f["type"], method="lr", days=20)
                results.append({
                    "code": f["code"],
                    "name": f["name"],
                    "type": f["type"],
                    "annual_return": hist.get("annual_return_pct", 0),
                    "max_drawdown": hist.get("max_drawdown_pct", 0),
                    "sharpe": hist.get("sharpe_ratio", 0),
                    "estimated_nav": est.get("estimated_nav"),
                    "estimated_change_pct": est.get("combined_change_pct", 0),
                    "trend": est.get("methods", {}).get("trend", {}).get("trend", "unknown"),
                })
            except Exception as e:
                print(f"[ERROR] 生成市场概览失败 ({f['code']}): {e}")
        
        return results
    
    def generate_portfolio_report(self, holdings):
        """生成组合报告"""
        portfolio_result = self.portfolio.calculate_portfolio(holdings)
        
        # 为每个持仓添加历史指标
        for item in portfolio_result.get("holdings", []):
            try:
                hist = self.portfolio.calculate_historical_returns(
                    item["code"], item["type"], period_days=252
                )
                item["history"] = hist
            except Exception:
                item["history"] = {}
        
        return portfolio_result
    
    def generate_fund_detail_report(self, fund_code, fund_type="cn"):
        """生成单基金深度报告"""
        # 获取历史数据
        if fund_type == "cn":
            end_date = datetime.now().strftime("%Y%m%d")
            start_date = (datetime.now() - timedelta(days=365)).strftime("%Y%m%d")
            df = self.ts_client.get_fund_nav(fund_code, start_date=start_date, end_date=end_date)
        else:
            df = self.yh_client.get_ticker_data(fund_code, period="1y")
            if df is not None and not df.empty:
                df = df.reset_index()
                df["unit_nav"] = df["Close"]
        
        if df is None or df.empty:
            return {"error": "无法获取数据"}
        
        navs = df["unit_nav"].astype(float).values
        
        # 各种预测
        trend = self.estimator.estimate_by_trend(df, method="lr", days=30)
        mc = PredictionModels.monte_carlo_simulation(navs, days=30, simulations=500)
        bb = PredictionModels.bollinger_bands(navs, window=20)
        ensemble = PredictionModels.multi_model_ensemble(navs)
        
        # 历史指标
        hist = self.portfolio.calculate_historical_returns(fund_code, fund_type, period_days=252)
        
        # 风险分析
        risk = self.risk_analyzer.analyze_single_fund(navs, name=fund_code)
        
        # 技术指标
        tech = {}
        try:
            # 仅以真实净值为收盘价构造序列（开高低未知时不伪造）
            df_sorted = df.sort_values("nav_date") if "nav_date" in df.columns else df
            close = df_sorted["unit_nav"].astype(float).values
            open_p = close
            high = close
            low = close
            volume = [0] * len(close)

            tech_result = self.tech_indicators.compute_all({
                "close": close, "open": open_p, "high": high, "low": low, "volume": volume
            })
            tech = {
                "signals": tech_result["signals"],
                "metadata": tech_result["metadata"],
            }
        except Exception as e:
            tech = {"error": str(e)}
        
        return {
            "fund_code": fund_code,
            "fund_type": fund_type,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "trend_analysis": trend,
            "monte_carlo": mc,
            "bollinger_bands": bb,
            "ensemble_prediction": ensemble,
            "historical_metrics": hist,
            "risk_analysis": risk,
            "technical_indicators": tech,
        }
    
    def to_html(self, report_data, report_type="overview"):
        """将报告数据转为HTML"""
        if report_type == "overview":
            return self._overview_html(report_data)
        elif report_type == "portfolio":
            return self._portfolio_html(report_data)
        elif report_type == "fund_detail":
            return self._fund_detail_html(report_data)
        else:
            return "<html><body><h1>Unknown report type</h1></body></html>"
    
    def _overview_html(self, data):
        """市场概览HTML"""
        rows = ""
        for item in data:
            trend_color = "green" if item.get("trend") == "up" else "red" if item.get("trend") == "down" else "gray"
            rows += f"""
            <tr>
                <td>{item['code']}</td>
                <td>{item['name']}</td>
                <td>{item['type']}</td>
                <td>{item.get('annual_return', 0)}%</td>
                <td>{item.get('max_drawdown', 0)}%</td>
                <td>{item.get('sharpe', 0)}</td>
                <td style="color:{trend_color}">{item.get('estimated_change_pct', 0)}%</td>
                <td>{item.get('trend', 'unknown')}</td>
            </tr>
            """
        
        return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>基金市场概览报告</title>
<style>
body {{ font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }}
.container {{ max-width: 1200px; margin: 0 auto; background: white; padding: 20px; border-radius: 8px; }}
h1 {{ color: #333; border-bottom: 2px solid #4CAF50; padding-bottom: 10px; }}
table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #ddd; }}
th {{ background: #4CAF50; color: white; }}
tr:hover {{ background: #f1f1f1; }}
.green {{ color: #4CAF50; }}
.red {{ color: #f44336; }}
.gray {{ color: #999; }}
.meta {{ color: #666; font-size: 12px; margin-top: 10px; }}
</style>
</head>
<body>
<div class="container">
<h1>📊 基金市场概览报告</h1>
<p class="meta">生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
<table>
<tr><th>代码</th><th>名称</th><th>市场</th><th>年化收益</th><th>最大回撤</th><th>夏普比率</th><th>估算变动</th><th>趋势</th></tr>
{rows}
</table>
</div>
</body>
</html>"""
    
    def _portfolio_html(self, data):
        """组合报告HTML"""
        if "error" in data:
            return f"<html><body><h1>错误</h1><p>{data['error']}</p></body></html>"
        
        rows = ""
        for item in data.get("holdings", []):
            profit_color = "green" if item.get("profit", 0) >= 0 else "red"
            rows += f"""
            <tr>
                <td>{item['code']}</td>
                <td>{item['name']}</td>
                <td>{item['type']}</td>
                <td>{item['shares']}</td>
                <td>{item['cost_price']}</td>
                <td>{item.get('current_price', 'N/A')}</td>
                <td>{item['cost_value']}</td>
                <td>{item['market_value']}</td>
                <td style="color:{profit_color}">{item['profit']} ({item['profit_pct']}%)</td>
                <td>{item['weight']}%</td>
            </tr>
            """
        
        total_color = "green" if data.get("total_profit", 0) >= 0 else "red"
        
        return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>投资组合报告</title>
<style>
body {{ font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }}
.container {{ max-width: 1200px; margin: 0 auto; background: white; padding: 20px; border-radius: 8px; }}
h1 {{ color: #333; border-bottom: 2px solid #2196F3; padding-bottom: 10px; }}
.summary {{ display: flex; gap: 20px; margin: 20px 0; }}
.card {{ background: #f9f9f9; padding: 15px; border-radius: 6px; flex: 1; text-align: center; }}
.card h3 {{ margin: 0 0 10px 0; color: #666; font-size: 14px; }}
.card .value {{ font-size: 24px; font-weight: bold; color: #333; }}
table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
th, td {{ padding: 10px; text-align: left; border-bottom: 1px solid #ddd; font-size: 14px; }}
th {{ background: #2196F3; color: white; }}
tr:hover {{ background: #f1f1f1; }}
.green {{ color: #4CAF50; }}
.red {{ color: #f44336; }}
.meta {{ color: #666; font-size: 12px; margin-top: 10px; }}
</style>
</head>
<body>
<div class="container">
<h1>💼 投资组合报告</h1>
<p class="meta">生成时间: {data.get('timestamp', '')}</p>
<div class="summary">
<div class="card"><h3>总成本</h3><div class="value">¥{data.get('total_cost', 0):,.2f}</div></div>
<div class="card"><h3>总市值</h3><div class="value">¥{data.get('total_value', 0):,.2f}</div></div>
<div class="card"><h3>总收益</h3><div class="value" style="color:{total_color}">¥{data.get('total_profit', 0):,.2f} ({data.get('total_profit_pct', 0)}%)</div></div>
</div>
<table>
<tr><th>代码</th><th>名称</th><th>类型</th><th>份额</th><th>成本价</th><th>现价</th><th>成本</th><th>市值</th><th>收益</th><th>权重</th></tr>
{rows}
</table>
</div>
</body>
</html>"""
    
    def _fund_detail_html(self, data):
        """单基金深度报告HTML"""
        if "error" in data:
            return f"<html><body><h1>错误</h1><p>{data['error']}</p></body></html>"
        
        trend = data.get("trend_analysis", {})
        mc = data.get("monte_carlo", {})
        bb = data.get("bollinger_bands", {})
        ensemble = data.get("ensemble_prediction", {})
        hist = data.get("historical_metrics", {})
        
        return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>基金深度报告 - {data['fund_code']}</title>
<style>
body {{ font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }}
.container {{ max-width: 900px; margin: 0 auto; background: white; padding: 20px; border-radius: 8px; }}
h1 {{ color: #333; border-bottom: 2px solid #FF9800; padding-bottom: 10px; }}
h2 {{ color: #555; font-size: 18px; margin-top: 25px; }}
.section {{ background: #fafafa; padding: 15px; border-radius: 6px; margin: 15px 0; }}
.metric {{ display: inline-block; margin: 10px 20px 10px 0; }}
.metric .label {{ color: #666; font-size: 12px; }}
.metric .value {{ font-size: 20px; font-weight: bold; color: #333; }}
.green {{ color: #4CAF50; }}
.red {{ color: #f44336; }}
.meta {{ color: #666; font-size: 12px; margin-top: 10px; }}
</style>
</head>
<body>
<div class="container">
<h1>📈 基金深度报告: {data['fund_code']}</h1>
<p class="meta">生成时间: {data.get('timestamp', '')}</p>

<div class="section">
<h2>历史表现</h2>
<div class="metric"><div class="label">总收益</div><div class="value">{hist.get('total_return_pct', 0)}%</div></div>
<div class="metric"><div class="label">年化收益</div><div class="value">{hist.get('annual_return_pct', 0)}%</div></div>
<div class="metric"><div class="label">年化波动</div><div class="value">{hist.get('annual_volatility_pct', 0)}%</div></div>
<div class="metric"><div class="label">最大回撤</div><div class="value">{hist.get('max_drawdown_pct', 0)}%</div></div>
<div class="metric"><div class="label">夏普比率</div><div class="value">{hist.get('sharpe_ratio', 0)}</div></div>
</div>

<div class="section">
<h2>趋势估算</h2>
<div class="metric"><div class="label">最新净值</div><div class="value">{trend.get('last_nav', 'N/A')}</div></div>
<div class="metric"><div class="label">估算净值</div><div class="value">{trend.get('estimated_nav', 'N/A')}</div></div>
<div class="metric"><div class="label">预测变动</div><div class="value">{trend.get('predicted_change_pct', 0)}%</div></div>
<div class="metric"><div class="label">置信度</div><div class="value">{trend.get('confidence', 0)}</div></div>
</div>

<div class="section">
<h2>多模型集成预测</h2>
<div class="metric"><div class="label">集成预测</div><div class="value">{ensemble.get('ensemble', 'N/A')}</div></div>
<div class="metric"><div class="label">预测变动</div><div class="value">{ensemble.get('expected_change_pct', 0)}%</div></div>
</div>

<div class="section">
<h2>蒙特卡洛模拟 (30天)</h2>
<div class="metric"><div class="label">预期净值</div><div class="value">{mc.get('expected_nav', 'N/A')}</div></div>
<div class="metric"><div class="label">上涨概率</div><div class="value">{mc.get('prob_up', 0)}%</div></div>
<div class="metric"><div class="label">预期收益</div><div class="value">{mc.get('expected_return_pct', 0)}%</div></div>
</div>

<div class="section">
<h2>布林带分析</h2>
<div class="metric"><div class="label">上轨</div><div class="value">{bb.get('upper_band', 'N/A')}</div></div>
<div class="metric"><div class="label">中轨</div><div class="value">{bb.get('middle_band', 'N/A')}</div></div>
<div class="metric"><div class="label">下轨</div><div class="value">{bb.get('lower_band', 'N/A')}</div></div>
<div class="metric"><div class="label">信号</div><div class="value">{bb.get('signal', 'N/A')}</div></div>
</div>
</div>
</body>
</html>"""
    
    def save_report(self, report_data, report_type, filename=None):
        """保存报告到文件"""
        if filename is None:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{report_type}_{ts}.html"
        
        path = os.path.join(REPORT_DIR, filename)
        html = self.to_html(report_data, report_type)
        
        with open(path, "w", encoding="utf-8") as f:
            f.write(html)
        
        # 同时保存JSON
        json_path = path.replace(".html", ".json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(report_data, f, ensure_ascii=False, indent=2, default=str)
        
        print(f"[INFO] 报告已保存: {path}")
        return path


if __name__ == "__main__":
    gen = ReportGenerator()
    
    print("=== 生成市场概览报告 ===")
    overview = gen.generate_market_overview()
    path = gen.save_report(overview, "overview", "market_overview_demo.html")
    print(f"报告路径: {path}")
    
    print("\n=== 生成组合报告 ===")
    holdings = [
        {"code": "510300.SH", "name": "沪深300ETF", "type": "cn_fund", "shares": 1000, "cost_price": 3.5, "market": "CN"},
        {"code": "SPY", "name": "SPDR S&P 500", "type": "us_fund", "shares": 50, "cost_price": 450, "market": "US"},
    ]
    portfolio = gen.generate_portfolio_report(holdings)
    gen.save_report(portfolio, "portfolio", "portfolio_demo.html")
    
    print("\n=== 生成单基金深度报告 ===")
    detail = gen.generate_fund_detail_report("510300.SH", "cn")
    gen.save_report(detail, "fund_detail", "fund_detail_demo.html")
