"""
FUND-OS 付费墙守卫（P0-2 修复核心）

将「计费身份」与「登录用户」强绑定，并对付费能力做 功能/配额 门禁：
- 未登录 → 401
- 功能未开放（当前套餐） → 402 + 升级提示
- 配额超限 → 429

用法（在蓝图视图函数上装饰）：
    @bp.route('/api/backtest/run', methods=['POST'])
    @require_subscription(feature='backtest')
    def run_backtest(): ...
"""
import functools
from typing import Optional

from flask import request, g, jsonify

from fund_estimation_system.core.auth import verify_token
from fund_estimation_system.data_fetcher.payment_service import get_payment_service


def _authenticate() -> Optional[dict]:
    auth = request.headers.get('Authorization', '')
    if not auth.startswith('Bearer '):
        return None
    return verify_token(auth[7:], token_type='access')


def require_subscription(feature: str = None, quota: str = None, n: int = 1):
    """功能/配额 门禁装饰器。

    feature: 需要的能力键（见 PLANS[...].features），如 'backtest' / 'valuation' / 'export'
    quota:   需要扣减的每日配额键，如 'backtest_per_day'
    """
    def decorator(f):
        @functools.wraps(f)
        def wrapper(*args, **kwargs):
            payload = _authenticate()
            if not payload:
                return jsonify({
                    'success': False, 'code': 401001,
                    'message': '未授权，请先登录', 'data': None,
                }), 401

            g.user_id = payload.get('sub')
            g.user_role = payload.get('role')
            g.username = payload.get('username')

            svc = get_payment_service()
            sub = svc.get_effective_subscription(g.user_id)

            if feature and not svc.has_feature(feature, sub):
                plan_now = svc.get_plan(sub['plan']) or {'name': '免费版', 'code': 'free'}
                return jsonify({
                    'success': False, 'code': 402001,
                    'message': f'当前套餐（{plan_now["name"]}）未开放该能力，请升级',
                    'reason': 'feature_locked',
                    'current_plan': plan_now['code'],
                    'upgrade_url': '/pricing',
                }), 402

            if quota:
                ok, info = svc.consume_quota(quota, sub['scope_type'], sub['scope_id'], n=n)
                if not ok:
                    return jsonify({
                        'success': False, 'code': 429001,
                        'message': '今日配额已用尽', 'reason': 'quota_exceeded',
                        'quota': info,
                    }), 429

            return f(*args, **kwargs)
        return wrapper
    return decorator
