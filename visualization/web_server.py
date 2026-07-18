# -*- coding: utf-8 -*-
"""Flask Web 可视化服务（应用工厂）。

架构说明：
- 路由按业务域拆分到 visualization/blueprints/ 下各蓝图，本文件仅负责：
  1) 构建 Flask app（工厂模式，便于测试与多 worker 部署）
  2) 持有全局单例客户端（estimator / tdx / 告警 / 自选 / 审计）
  3) 注册蓝图与就绪/健康检查端点
- 蓝图通过 `from fund_estimation_system.visualization.web_server import app` 反向引用单例，
  避免循环导入：本模块先定义单例，再 import 蓝图并注册。
"""
import os
import sys

# 确保项目根目录在路径中
_CURRENT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PARENT_DIR = os.path.dirname(_CURRENT_DIR)
if _PARENT_DIR not in sys.path:
    sys.path.insert(0, _PARENT_DIR)

from flask import Flask

from fund_estimation_system import config
from fund_estimation_system.estimator.fund_nav_estimator import FundNavEstimator
from fund_estimation_system.estimator.portfolio_calculator import PortfolioCalculator
from fund_estimation_system.estimator.risk_analyzer import FundRiskAnalyzer
from fund_estimation_system.estimator.valuation_backtest import ValuationBacktest
from fund_estimation_system.report_generator.daily_report import ReportGenerator
from fund_estimation_system.data_fetcher.tdx_realtime import get_client as get_tdx_realtime_client
from fund_estimation_system.data_fetcher.realtime_service import (
    get_alert_engine, get_watchlist_store, get_audit_logger,
)


def create_app():
    app = Flask(__name__,
        template_folder=os.path.join(os.path.dirname(__file__), "templates"),
        static_folder=os.path.join(os.path.dirname(__file__), "static"))

    # 注册蓝图（按业务域拆分）
    from fund_estimation_system.visualization.blueprints.fund_bp import bp as fund_bp
    from fund_estimation_system.visualization.blueprints.analysis_bp import bp as analysis_bp
    from fund_estimation_system.visualization.blueprints.realtime_bp import bp as realtime_bp
    from fund_estimation_system.visualization.blueprints.ops_bp import bp as ops_bp
    from fund_estimation_system.visualization.blueprints.l2_bp import bp as l2_bp
    from fund_estimation_system.visualization.blueprints.push_bp import bp as push_bp
    from fund_estimation_system.visualization.blueprints.ha_bp import bp as ha_bp
    from fund_estimation_system.visualization.blueprints.tenant_bp import bp as tenant_bp
    from fund_estimation_system.visualization.blueprints.billing_bp import bp as billing_bp
    from fund_estimation_system.visualization.blueprints.admin_bp import bp as admin_bp
    from fund_estimation_system.visualization.blueprints.auth_bp import bp as auth_bp
    from fund_estimation_system.visualization.blueprints.legal_bp import bp as legal_bp

    app.register_blueprint(fund_bp)
    app.register_blueprint(analysis_bp)
    app.register_blueprint(realtime_bp)
    app.register_blueprint(ops_bp)
    app.register_blueprint(l2_bp)
    app.register_blueprint(push_bp)
    app.register_blueprint(ha_bp)
    app.register_blueprint(tenant_bp)
    app.register_blueprint(billing_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(legal_bp)

    # 确保数据库表存在（create_all 幂等；生产亦由 docker entrypoint 预建）
    try:
        from fund_estimation_system.models.database import init_db
        init_db()
    except Exception as e:  # noqa: BLE001
        print(f"[WARN] 初始化数据库失败（运行时将按需建表）: {e}")

    # 全局 API 限流（Redis 优先，未配置则进程内兜底）
    try:
        from fund_estimation_system.core.rate_limiter import (
            register_rate_limit_middleware,
        )
        register_rate_limit_middleware(
            app, global_per_min=config.RATE_LIMIT_GLOBAL_PER_MIN)
    except Exception as e:  # noqa: BLE001
        print(f"[WARN] 限流中间件初始化失败（已跳过）: {e}")

    return app


# 全局单例客户端（被各蓝图 import 使用）
estimator = FundNavEstimator()
portfolio_calc = PortfolioCalculator()
risk_analyzer = FundRiskAnalyzer()
valuation_bt = ValuationBacktest()
report_gen = ReportGenerator()
tdx_realtime = get_tdx_realtime_client()
alert_engine = get_alert_engine()
watchlist_store = get_watchlist_store()
audit_logger = get_audit_logger()

# 应用实例（供 `flask` / `gunicorn` 使用，变量名需为 app）
app = create_app()


if __name__ == "__main__":
    print(f"=" * 50)
    print(" 基金估算系统 Web 服务启动")
    print(f"访问地址: http://{config.WEB_HOST}:{config.WEB_PORT}")
    print(f"演示模式: {'开启' if config.DEMO_MODE else '关闭'}")
    print(f"=" * 50)
    # 生产部署建议：gunicorn -w 4 -b 0.0.0.0:5000 web_server:app
    app.run(host=config.WEB_HOST, port=config.WEB_PORT, debug=False)
