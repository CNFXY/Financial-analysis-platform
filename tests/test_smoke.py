"""
web_server 端到端冒烟测试：
1. 全局限流中间件真实命中：直接复用 create_app 调用的同一函数
   register_rate_limit_middleware，构造小阈值后连续请求应 200→200→429。
2. create_app 在「完整依赖」下能起来（真实闸门）：
   - 生产/CI 装了 pandas/tushare 等重型依赖时，本测试会真正启动应用工厂、
     校验返回 Flask 实例且全局限流 before_request 已挂载。
   - 本机若缺重型依赖（如 pandas），importorskip 会优雅跳过，不会红。
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)            # fund_estimation_system
WS = os.path.dirname(ROOT)              # workspace
for p in (WS, ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)

# 必须在导入任何模块前固定环境
# DATABASE_URL 由 conftest 统一设为一次性临时库，此处不再覆盖。
os.environ['JWT_SECRET'] = 'test-secret-for-smoke-0123456789abcdef'
os.environ['WEB_DEBUG'] = 'True'
os.environ['PAYMENT_MODE'] = 'sandbox'
os.environ.pop('REDIS_URL', None)

import pytest  # noqa: E402
from flask import Flask, jsonify  # noqa: E402
from fund_estimation_system.core.rate_limiter import (  # noqa: E402
    register_rate_limit_middleware,
)

# 正式常驻回归用例
pytestmark = pytest.mark.regression


def test_global_rate_limit_middleware_fires():
    """全局限流中间件（与 create_app 同款）真实命中 429。"""
    app = Flask(__name__)
    app.config.update(TESTING=True)
    register_rate_limit_middleware(app, global_per_min=2, window_seconds=60)

    @app.route('/api/ping')
    def ping():
        return jsonify({'ok': True})

    @app.route('/healthz')  # 必须在首次请求前注册
    def healthz():
        return 'ok'

    c = app.test_client()
    assert c.get('/api/ping').status_code == 200
    assert c.get('/api/ping').status_code == 200
    # 第 3 次超过全局阈值 → 429
    r = c.get('/api/ping')
    assert r.status_code == 429, r.get_data(as_text=True)
    assert r.headers.get('Retry-After') is not None

    # 非 /api 路径不受限（如健康检查/页面）
    assert c.get('/healthz').status_code == 200


def test_create_app_boots(monkeypatch):
    """应用工厂在完整依赖下可启动（缺重型依赖时跳过）。

    这是「生产可达性闸门」：CI 装齐依赖后此测试会真正执行 create_app，
    确保蓝图/限流/DB 初始化链路在真实栈下不崩。
    """
    web_server = pytest.importorskip(
        'fund_estimation_system.visualization.web_server')
    from flask import Flask
    import fund_estimation_system.core.rate_limiter as _rl
    import fund_estimation_system.config as _cfg

    # 隔离：清空进程级限流单例的累积计数，并将全局阈值临时调高，
    # 避免前序测试的 /api 请求把全局限流计数顶到 429（限流命中已由
    # test_global_rate_limit_middleware_fires 单独验证）。
    monkeypatch.setattr(_cfg, 'RATE_LIMIT_GLOBAL_PER_MIN', 10_000_000)
    if _rl._default_limiter is not None:
        _rl._default_limiter._mem.clear()

    app = web_server.create_app()
    assert isinstance(app, Flask), "create_app 应返回 Flask 实例"

    # 全局限流 before_request 已挂载
    funcs = app.before_request_funcs.get(None, [])
    assert any(getattr(f, '__name__', '') == '_global_rate_limit' for f in funcs), \
        "全局限流 before_request 未注册"

    # 一个真实可路由的轻量接口（auth 蓝图不依赖数据源）应可访问
    client = app.test_client()
    r = client.post('/api/auth/register', json={
        'username': 'smoke1', 'email': 'smoke1@example.com',
        'password': 'Smokepw0rd!'})
    assert r.status_code in (201, 409), r.get_data(as_text=True)
