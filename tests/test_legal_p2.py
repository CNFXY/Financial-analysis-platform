"""
P2 合规清单回归测试：
验证公开站点配置端点 /api/public/site-config 可匿名访问并返回合规字段
（站点名、运营主体、ICP/公安备案号、联系方式）。
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)            # fund_estimation_system
WS = os.path.dirname(ROOT)              # workspace
for p in (WS, ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)

os.environ.setdefault('JWT_SECRET', 'test-secret-for-p2-legal-0123456789abcdef')

from flask import Flask  # noqa: E402
import pytest  # noqa: E402
from fund_estimation_system.visualization.blueprints.legal_bp import bp as legal_bp  # noqa: E402

pytestmark = pytest.mark.regression


def _app():
    app = Flask(__name__)
    app.register_blueprint(legal_bp)
    return app


def test_site_config_public_and_shape():
    c = _app().test_client()
    r = c.get('/api/public/site-config')
    assert r.status_code == 200, r.get_data(as_text=True)
    d = r.get_json()
    for key in ('site_name', 'company_name', 'icp_beian',
                'police_beian', 'contact_email', 'service_tel'):
        assert key in d, f"缺少字段 {key}"
    from fund_estimation_system import config
    assert d['site_name'] == config.SITE_NAME


def test_site_config_no_auth_required():
    # 不带任何认证头也应可访问（公开信息）
    c = _app().test_client()
    r = c.get('/api/public/site-config', headers={})
    assert r.status_code == 200
