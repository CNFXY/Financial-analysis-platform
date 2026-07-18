"""
P1 回归测试：限流接 Redis（含内存兜底）+ 密码强度策略。
仅验证「限流核心 + 密码策略 + 接口接线」，不依赖 pandas/tushare。
"""
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)            # fund_estimation_system
WS = os.path.dirname(ROOT)              # workspace
for p in (WS, ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)

# 必须在导入任何模块前固定环境
# DATABASE_URL 由 conftest 统一设为一次性临时库，此处不再覆盖。
os.environ['JWT_SECRET'] = 'test-secret-for-p1-regression-0123456789abcdef'
os.environ['WEB_DEBUG'] = 'True'
os.environ['PAYMENT_MODE'] = 'sandbox'
# 放宽限流阈值，避免跨测试文件计数叠加导致偶发 429
os.environ['RATE_LIMIT_REGISTER_PER_MIN'] = '100'
os.environ['RATE_LIMIT_LOGIN_PER_MIN'] = '100'
# 确保走内存兜底（无 Redis）
os.environ.pop('REDIS_URL', None)

from flask import Flask, jsonify  # noqa: E402
from fund_estimation_system.core.auth import validate_password_strength  # noqa: E402
from fund_estimation_system.core.rate_limiter import (  # noqa: E402
    RateLimiter, rate_limit,
)
from fund_estimation_system.visualization.blueprints.auth_bp import bp as auth_bp  # noqa: E402
from fund_estimation_system.models.database import init_db  # noqa: E402

# 正式常驻回归用例
pytestmark = pytest.mark.regression


def _make_app():
    app = Flask(__name__)
    app.config.update(TESTING=True)
    app.register_blueprint(auth_bp)
    init_db()
    return app


# ==================== 密码强度策略 ====================
def test_password_policy_rules():
    v = validate_password_strength
    assert v('short')[0] is False, "过短应拒绝"
    assert v('weakpass')[0] is False, "仅小写(一类)应拒绝"
    assert v('aaaaaaaaaa')[0] is False, "全同字符应拒绝"
    assert v('AAAAAAAAAA')[0] is False, "一类+重复应拒绝"
    assert v('1234567890')[0] is False, "常见弱口令/连续序列应拒绝"
    assert v('password123')[0] is False, "常见弱口令应拒绝"
    assert v('Abcd123456!')[0] is False, "含连续递增序列应拒绝"
    # 通过案例
    assert v('Password12')[0] is True, "10位+三类应接受"
    assert v('P0passw0rd!')[0] is True
    assert v('Normalpw0rd!')[0] is True


# ==================== 注册接口强制策略 ====================
def test_register_rejects_weak_accepts_strong():
    app = _make_app()
    c = app.test_client()
    r = c.post('/api/auth/register', json={
        'username': 'weak1', 'email': 'weak1@example.com', 'password': 'short'})
    assert r.status_code == 400, r.get_data(as_text=True)
    r2 = c.post('/api/auth/register', json={
        'username': 'strong1', 'email': 'strong1@example.com',
        'password': 'Strongpw0rd!'})
    assert r2.status_code == 201, r2.get_data(as_text=True)


# ==================== 限流器：内存兜底逻辑 ====================
def test_rate_limiter_inmemory_allows_then_blocks():
    rl = RateLimiter()  # 无 REDIS_URL → 内存兜底
    assert rl.using_redis() is False
    for _ in range(5):
        ok, _rem, _retry = rl.allow('k', 5, 60)
        assert ok is True
    ok, _rem, retry = rl.allow('k', 5, 60)
    assert ok is False
    assert retry > 0


def test_rate_limiter_redis_unavailable_does_not_crash():
    # 即便给定 redis_url，连不上也应降级内存而非抛异常
    rl = RateLimiter(redis_url='redis://localhost:6379/0')
    ok, _rem, _retry = rl.allow('kr', 3, 60)
    assert ok is True


# ==================== 限流装饰器接线 ====================
def test_rate_limit_decorator_blocks_after_limit():
    app = Flask(__name__)

    @app.route('/hit')
    @rate_limit(max_requests=2, window_seconds=60, key_prefix='testhit')
    def hit():
        return jsonify({'ok': True})

    c = app.test_client()
    assert c.get('/hit').status_code == 200
    assert c.get('/hit').status_code == 200
    assert c.get('/hit').status_code == 429


# ==================== 改密接口：策略 + 旧密码校验 ====================
def test_change_password_flow():
    app = _make_app()
    c = app.test_client()
    reg = c.post('/api/auth/register', json={
        'username': 'chg1', 'email': 'chg1@example.com', 'password': 'Initpw0rd!'})
    assert reg.status_code == 201, reg.get_data(as_text=True)
    token = reg.get_json()['data']['access_token']
    h = {'Authorization': f'Bearer {token}'}

    # 新密码过弱 → 400
    r_weak = c.post('/api/auth/change-password', json={
        'old_password': 'Initpw0rd!', 'new_password': 'short'},
        headers=h)
    assert r_weak.status_code == 400, r_weak.get_data(as_text=True)

    # 旧密码错误 → 400
    r_old = c.post('/api/auth/change-password', json={
        'old_password': 'Wrongpw0rd!', 'new_password': 'Newpass0rd!'},
        headers=h)
    assert r_old.status_code == 400, r_old.get_data(as_text=True)

    # 正常改密 → 200，且新密码可登录
    r_ok = c.post('/api/auth/change-password', json={
        'old_password': 'Initpw0rd!', 'new_password': 'Newpass0rd!'},
        headers=h)
    assert r_ok.status_code == 200, r_ok.get_data(as_text=True)

    login = c.post('/api/auth/login', json={
        'username': 'chg1', 'password': 'Newpass0rd!'})
    assert login.status_code == 200, login.get_data(as_text=True)


if __name__ == '__main__':
    import pytest
    sys.exit(pytest.main([__file__, '-v']))
