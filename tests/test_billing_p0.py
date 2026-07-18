"""
P0 致命硬伤回归测试：
1. 认证不可伪造（强制 PyJWT 验签，错误密钥签发被拒）
2. 付费墙生效（未登录 401、免费账号付费能力 402、付费后通过）
3. 支付跨进程一致（订单/订阅落库，多实例读同一 DB 可见、回调幂等）

说明：本测试只验证「认证 + 计费 + 付费墙」三条链路（不依赖 pandas/tushare 等
数据源依赖），以最小化测试环境与真实部署的解耦。真实部署由 requirements.txt
提供完整依赖，web_server.create_app 注册全部蓝图。
"""
import os
import sys
import time

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)            # fund_estimation_system
WS = os.path.dirname(ROOT)              # workspace
for p in (WS, ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)

# 必须在导入任何模型/App 之前固定环境变量
# 注意：DATABASE_URL 由 conftest 统一设为一次性临时库，此处不再覆盖，
# 避免 models.database 引擎被缓存到错误文件导致表找不到。
os.environ['JWT_SECRET'] = 'test-secret-for-p0-regression-0123456789abcdef'
os.environ['WEB_DEBUG'] = 'True'
os.environ['PAYMENT_MODE'] = 'sandbox'

import jwt  # noqa: E402
from flask import Flask, Blueprint, jsonify  # noqa: E402
from fund_estimation_system.core.auth import JWT_SECRET  # noqa: E402
from fund_estimation_system.core.billing_guard import require_subscription  # noqa: E402
from fund_estimation_system.visualization.blueprints.auth_bp import bp as auth_bp  # noqa: E402
from fund_estimation_system.visualization.blueprints.billing_bp import bp as billing_bp  # noqa: E402
from fund_estimation_system.data_fetcher.payment_service import (  # noqa: E402
    get_payment_service, PaymentService,
)
from fund_estimation_system.models.database import init_db  # noqa: E402

# 正式常驻回归用例
pytestmark = pytest.mark.regression


def _make_app():
    app = Flask(__name__)
    app.config.update(TESTING=True)
    app.register_blueprint(auth_bp)
    app.register_blueprint(billing_bp)

    # 用守卫装饰一个模拟的「付费能力」接口（等价于 analysis_bp 的 backtest）
    tb = Blueprint('test_paywall', __name__)

    @tb.route('/api/backtest/run', methods=['POST'])
    @require_subscription(feature='backtest')
    def api_backtest_run():
        return jsonify({'ok': True, 'note': 'guard passed'})

    app.register_blueprint(tb)
    init_db()
    return app


def test_auth_forgery_rejected():
    """用错误密钥签发的 token 必须被拒绝（验证强制 PyJWT 验签）。"""
    forged = jwt.encode(
        {'sub': 'attacker', 'username': 'attacker', 'role': 'admin', 'type': 'access',
         'iat': int(time.time()), 'exp': int(time.time()) + 3600},
        'wrong-secret-but-32bytes-long-abcdefghijklmnop', algorithm='HS256',
    )
    app = _make_app()
    client = app.test_client()
    r1 = client.post('/api/backtest/run', json={'code': '510300.SH'})
    assert r1.status_code == 401, r1.get_data(as_text=True)
    r2 = client.post('/api/backtest/run', json={'code': '510300.SH'},
                    headers={'Authorization': f'Bearer {forged}'})
    assert r2.status_code == 401, r2.get_data(as_text=True)


def test_paywall_enforced():
    """免费登录用户无法使用付费能力（402），付费后通过。"""
    app = _make_app()
    client = app.test_client()

    reg = client.post('/api/auth/register', json={
        'username': 'p0user', 'email': 'p0@example.com', 'password': 'P0passw0rd!'})
    assert reg.status_code == 201, reg.get_data(as_text=True)
    token = reg.get_json()['data']['access_token']
    uid = reg.get_json()['data']['user']['id']
    headers = {'Authorization': f'Bearer {token}'}

    # 免费账号调用 backtest（专业版能力）→ 402
    r_free = client.post('/api/backtest/run', json={'code': '510300.SH'}, headers=headers)
    assert r_free.status_code == 402, r_free.get_data(as_text=True)

    # 模拟支付成功（沙箱回调）→ 订阅升级为 pro（落库）
    svc = get_payment_service()
    created = svc.create_order('pro', 'alipay_web', 'user', uid, user_id=uid)
    assert created['success']
    oid = created['order']['order_id']
    res = svc.handle_alipay_notify({
        'out_trade_no': oid, 'trade_status': 'TRADE_SUCCESS', 'trade_no': 'T' + oid})
    assert res['success'], res

    # 再次调用 backtest → 守卫通过（非 401/402）
    r_paid = client.post('/api/backtest/run', json={'code': '510300.SH'}, headers=headers)
    assert r_paid.status_code not in (401, 402), r_paid.get_data(as_text=True)


def test_payment_cross_process_consistent():
    """多实例（模拟多 worker）读写同一数据库，订单/订阅可见、回调幂等。"""
    svc_a = PaymentService()  # worker A
    svc_b = PaymentService()  # worker B（独立内存，但共享 DB）

    created = svc_a.create_order('pro', 'wechat_native', 'user', 'u_x', user_id='u_x')
    assert created['success']
    oid = created['order']['order_id']

    # 回调打到 worker B（不同实例）→ 仍能入账并激活订阅
    res = svc_b.handle_wechat_notify({
        'out_trade_no': oid, 'result_code': 'SUCCESS', 'transaction_id': 'WX' + oid})
    assert res['success'], res

    # worker A 重新读取，应看到已支付 + pro 订阅（证明跨进程一致）
    order = svc_a.get_order(oid)
    assert order['status'] == 'paid', order
    sub = svc_a.get_subscription('user', 'u_x')
    assert sub['plan'] == 'pro', sub

    # 幂等：重复回调不应重复入账（nonce 唯一约束兜底）
    res2 = svc_a.handle_wechat_notify({
        'out_trade_no': oid, 'result_code': 'SUCCESS', 'transaction_id': 'WX' + oid})
    assert res2['success'] and res2.get('note') == '重复通知已忽略', res2


def test_manual_activate_requires_admin():
    """手动激活仅限 admin。"""
    app = _make_app()
    client = app.test_client()
    r0 = client.post('/api/billing/activate', json={'tenant_id': 't1', 'plan': 'enterprise'})
    assert r0.status_code == 401
    reg = client.post('/api/auth/register', json={
        'username': 'normal', 'email': 'normal@example.com', 'password': 'Normalpw0rd!'})
    token = reg.get_json()['data']['access_token']
    r1 = client.post('/api/billing/activate', json={'tenant_id': 't1', 'plan': 'enterprise'},
                     headers={'Authorization': f'Bearer {token}'})
    assert r1.status_code == 403


if __name__ == '__main__':
    import pytest
    sys.exit(pytest.main([__file__, '-v']))
