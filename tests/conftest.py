"""
FUND-OS 测试配置与共享 Fixtures
"""

import os
import sys
import tempfile
from datetime import datetime, timedelta

import pytest

# 确保项目根目录在路径中
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ==================== 测试环境配置 ====================

# 使用一次性临时库（每个测试进程独立），避免：
# 1. 各测试文件各自设置 DATABASE_URL 互相覆盖、用户数据污染；
# 2. SQLite WAL 文件让脏数据跨运行残留。
# 必须在任何模块导入 models.database 之前设置好，引擎只构建一次。
_TEST_DB_DIR = tempfile.mkdtemp(prefix='fundos_test_')
_TEST_DB_PATH = os.path.join(_TEST_DB_DIR, 'test_fundos.db')
os.environ['DATABASE_URL'] = f'sqlite:///{_TEST_DB_PATH}'
os.environ['SECRET_KEY'] = 'test-secret-key-for-testing-only'
os.environ['REDIS_URL'] = ''  # 测试时禁用 Redis
os.environ['JWT_SECRET_KEY'] = 'test-jwt-secret'
os.environ['FLASK_ENV'] = 'testing'


@pytest.fixture(scope='session', autouse=True)
def _cleanup_test_db():
    """测试结束后清理临时库文件。"""
    yield
    for suffix in ('', '-wal', '-shm'):
        try:
            os.remove(_TEST_DB_PATH + suffix)
        except OSError:
            pass
    try:
        os.rmdir(_TEST_DB_DIR)
    except OSError:
        pass


# ==================== Flask App Fixture ====================

@pytest.fixture(scope='session')
def app():
    """创建测试用 Flask 应用"""
    from app import create_app
    
    app = create_app(testing=True)
    
    # 配置测试模式
    app.config.update({
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
        'WTF_CSRF_ENABLED': False,
        'DEBUG': True
    })
    
    return app


@pytest.fixture(scope='function')
def client(app):
    """创建测试客户端"""
    with app.test_client() as client:
        yield client


@pytest.fixture(scope='function')
def runner(app):
    """创建 CLI test runner"""
    return app.test_cli_runner()


# ==================== 数据库 Fixtures ====================

@pytest.fixture(autouse=True)
def db_session():
    """
    每个测试函数前自动创建/销毁数据库表。
    autouse=True 表示所有测试都会自动应用此 fixture。
    仅依赖引擎，不依赖已废弃的 app fixture。
    """
    from models import Base
    from models.database import engine
    
    # 创建所有表
    Base.metadata.create_all(bind=engine)
    
    yield  # 执行测试
    
    # 清理：删除所有表
    Base.metadata.drop_all(bind=engine)


# ==================== 认证 Fixtures ====================

@pytest.fixture
def auth_headers(client):
    """
    返回有效的 JWT 认证头（已注册并登录的用户）
    """
    # 注册用户
    register_resp = client.post('/api/v1/auth/register', json={
        'username': 'testuser',
        'email': 'test@example.com',
        'password': 'TestPass123!'
    })
    
    data = register_resp.get_json()
    token = data['data']['access_token']
    
    return {'Authorization': f'Bearer {token}'}


@pytest.fixture
def admin_auth_headers(client):
    """返回管理员认证头"""
    # 注册管理员
    from models import User
    user = User.create(
        username='admin_test',
        email='admin@test.com',
        password='AdminPass123!',
        role='admin'
    )
    
    from core.auth import generate_tokens
    tokens = generate_tokens(user.id)
    
    return {'Authorization': f'Bearer {tokens["access_token"]}'}


# ==================== 测试数据 Fixtures ====================

@pytest.fixture
def sample_user():
    """返回一个示例用户对象"""
    from models import User
    return User(
        id=1,
        username='testuser',
        email='test@example.com',
        hashed_password='$2b$12$hash_placeholder',
        role='user',
        is_active=True
    )


@pytest.fixture
def sample_fund():
    """返回一个示例基金对象"""
    from models import FundInfo
    return FundInfo(
        code='000001',
        name='华夏成长混合',
        fund_type='mixed',
        nav=1.2345,
        nav_date=datetime.now().date(),
        manager='张三',
        company='华夏基金',
        established_date=datetime(2015, 1, 15).date()
    )


@pytest.fixture
def sample_portfolio(sample_user):
    """返回一个示例投资组合"""
    from models import Portfolio
    portfolio = Portfolio(
        id=1,
        user_id=sample_user.id,
        name='我的基金组合',
        description='测试组合',
        is_default=True
    )
    portfolio.holdings = []
    return portfolio


@pytest.fixture
def sample_nav_history():
    """返回示例净值历史数据"""
    dates = [
        datetime.now().date() - timedelta(days=i)
        for i in range(30)
    ]
    
    base_value = 1.2000
    history = []
    for i, date in enumerate(dates):
        import random
        value = base_value + (random.random() - 0.5) * 0.05
        history.append({
            'date': date.isoformat(),
            'nav': round(value, 4),
            'accumulated_nav': round(value * 1.5, 4),
            'daily_change_pct': round((value - base_value) / base_value * 100, 2) if i > 0 else 0
        })
        base_value = value
    
    return history


# ==================== Mock 数据源 Fixtures ====================

@pytest.fixture
def mock_tushare_api(mocker):
    """Mock Tushare API 调用"""
    def mock_get(*args, **kwargs):
        class FakeDataFrame:
            def __init__(self):
                self.data = [{
                    'ts_code': '000001.OF',
                    'name': '华夏成长混合',
                    'nav_date': datetime.now().strftime('%Y%m%d'),
                    'unit_nav': '1.2345',
                    'accum_nav': '1.8517',
                    'daily_profit': '0.0023'
                }]
            
            @property
            def empty(self):
                return len(self.data) == 0
            
            def to_dict(self, orient='records'):
                return self.data
        
        return FakeDataFrame()
    
    mocker.patch('tushare.pro_api.pro_bar', side_effect=mock_get)
    mocker.patch('tushare.fund_basic', side_effect=mock_get)


@pytest.fixture
def mock_redis(mocker):
    """Mock Redis 连接"""
    fake_redis = {
        'cache': {},
        'expired_at': {}
    }
    
    class FakeRedis:
        def get(self, key):
            return fake_redis['cache'].get(key)
        
        def set(self, key, value, ex=None):
            fake_redis['cache'][key] = value
            if ex:
                fake_redis['expired_at'][key] = ex
        
        def delete(self, *keys):
            for k in keys:
                fake_redis['cache'].pop(k, None)
        
        def ping(self):
            return True
    
    mocker.patch('core.cache.redis_client', FakeRedis())
    return FakeRedis()


# ==================== 辅助函数 ====================

class APIHelper:
    """API 测试辅助类，封装常用操作"""
    
    def __init__(self, client, auth_headers=None):
        self.client = client
        self.auth_headers = auth_headers or {}
    
    def get(self, path: str, **kwargs):
        resp = self.client.get(path, headers=self.auth_headers, **kwargs)
        return resp.get_json(), resp.status_code
    
    def post(self, path: str, json=None, **kwargs):
        resp = self.client.post(path, 
                               json=json, 
                               headers=self.auth_headers, 
                               **kwargs)
        return resp.get_json(), resp.status_code
    
    def put(self, path: str, json=None, **kwargs):
        resp = self.client.put(path, 
                              json=json, 
                              headers=self.auth_headers, 
                              **kwargs)
        return resp.get_json(), resp.status_code
    
    def delete(self, path: str, **kwargs):
        resp = self.client.delete(path, 
                                 headers=self.auth_headers, 
                                 **kwargs)
        return resp.get_json(), resp.status_code
    
    def assert_success(self, response_data, status_code=200):
        assert status_code < 400, f"Expected success but got {status_code}: {response_data}"
        assert response_data.get('success') is True
        return response_data.get('data')
    
    def assert_error(self, response_data, expected_status_code, expected_error=None):
        assert response_data.get('success') is False
        if expected_error:
            assert expected_error.lower() in response_data.get('error', '').lower()


@pytest.fixture
def api(client, auth_headers):
    """提供 API 测试辅助实例"""
    return APIHelper(client, auth_headers)
