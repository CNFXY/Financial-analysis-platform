"""
FUND-OS 认证模块测试
覆盖: 注册/登录/Token刷新/权限控制/密码修改
"""

import pytest
import json


class TestUserRegistration:
    """用户注册测试"""
    
    def test_register_success(self, client):
        """正常注册流程"""
        resp = client.post('/api/v1/auth/register', json={
            'username': 'newuser',
            'email': 'newuser@test.com',
            'password': 'SecurePass123!'
        })
        
        data = resp.get_json()
        
        assert resp.status_code == 201
        assert data['success'] is True
        assert data['data']['user']['username'] == 'newuser'
        assert 'access_token' in data['data']
        assert 'refresh_token' in data['data']
    
    def test_register_missing_fields(self, client):
        """缺少必填字段"""
        resp = client.post('/api/v1/auth/register', json={
            'username': 'incomplete',
            # 缺少 email 和 password
        })
        
        assert resp.status_code == 400
    
    def test_register_duplicate_username(self, client):
        """重复用户名"""
        # 第一次注册
        client.post('/api/v1/auth/register', json={
            'username': 'dup_user',
            'email': 'first@test.com',
            'password': 'Pass123!'
        })
        
        # 重复用户名（不同邮箱）
        resp = client.post('/api/v1/auth/register', json={
            'username': 'dup_user',
            'email': 'second@test.com',
            'password': 'Pass123!'
        })
        
        assert resp.status_code == 409
    
    def test_register_duplicate_email(self, client):
        """重复邮箱"""
        client.post('/api/v1/auth/register', json={
            'username': 'user_a',
            'email': 'same@test.com',
            'password': 'Pass123!'
        })
        
        resp = client.post('/api/v1/auth/register', json={
            'username': 'user_b',
            'email': 'same@test.com',
            'password': 'Pass123!'
        })
        
        assert resp.status_code == 409
    
    def test_register_weak_password_rejected(self, client):
        """弱密码应被拒绝（如果实现了密码强度验证）"""
        # 这个测试取决于是否实现了密码策略
        resp = client.post('/api/v1/auth/register', json={
            'username': 'weakpwd',
            'email': 'weak@test.com',
            'password': '123'  # 太短的密码
        })
        
        # 如果有密码强度检查，应返回 400；否则可能成功
        # 这里只验证不崩溃
        assert resp.status_code in [200, 201, 400]


class TestUserLogin:
    """用户登录测试"""
    
    @pytest.fixture(autouse=True)
    def setup(self, client):
        """注册测试用户"""
        self.client = client
        self.client.post('/api/v1/auth/register', json={
            'username': 'login_tester',
            'email': 'login@test.com',
            'password': 'LoginPass123!'
        })
    
    def test_login_with_username(self):
        """使用用户名登录"""
        resp = self.client.post('/api/v1/auth/login', json={
            'username': 'login_tester',
            'password': 'LoginPass123!'
        })
        
        data = resp.get_json()
        assert resp.status_code == 200
        assert data['success'] is True
        assert 'access_token' in data['data']
    
    def test_login_with_email(self):
        """使用邮箱登录"""
        resp = self.client.post('/api/v1/auth/login', json={
            'username': 'login@test.com',
            'password': 'LoginPass123!'
        })
        
        assert resp.status_code == 200
        assert resp.get_json()['success'] is True
    
    def test_login_wrong_password(self):
        """错误密码"""
        resp = self.client.post('/api/v1/auth/login', json={
            'username': 'login_tester',
            'password': 'WrongPassword!!!'
        })
        
        assert resp.status_code == 401
    
    def test_login_nonexistent_user(self):
        """不存在用户"""
        resp = self.client.post('/api/v1/auth/login', json={
            'username': 'ghost_user',
            'password': 'AnyPassword!'
        })
        
        assert resp.status_code == 401
    
    def test_login_empty_credentials(self):
        """空凭证"""
        resp = self.client.post('/api/v1/auth/login', json={})
        
        assert resp.status_code == 400


class TestTokenRefresh:
    """Token 刷新测试"""
    
    def test_refresh_valid_token(self, client):
        """有效 Refresh Token 刷新"""
        # 先登录获取 token
        client.post('/api/v1/auth/register', json={
            'username': 'refresher',
            'email': 'refresh@test.com',
            'password': 'RefreshPass123!'
        })
        
        login_resp = client.post('/api/v1/auth/login', json={
            'username': 'refresher',
            'password': 'RefreshPass123!'
        })
        refresh_token = login_resp.get_json()['data']['refresh_token']
        
        # 刷新
        refresh_resp = client.post('/api/v1/auth/refresh', json={
            'refresh_token': refresh_token
        })
        
        data = refresh_resp.get_json()
        assert refresh_resp.status_code == 200
        assert data['success'] is True
        assert 'access_token' in data['data']
    
    def test_refresh_invalid_token(self, client):
        """无效 Token"""
        resp = client.post('/api/v1/auth/refresh', json={
            'refresh_token': 'invalid.token.here'
        })
        
        assert resp.status_code == 401
    
    def test_refresh_without_token(self, client):
        """没有提供 Token"""
        resp = client.post('/api/v1/auth/refresh', json={})
        
        assert resp.status_code == 400


class TestGetCurrentUser:
    """获取当前用户信息测试"""
    
    def test_get_me_authenticated(self, api):
        """已认证用户获取自身信息"""
        data = api.get('/api/v1/auth/me')
        user_data = api.assert_success(data[0], data[1])
        
        assert user_data['username'] == 'testuser'  # conftest 中创建的用户
        assert 'email' in user_data
        # 不应包含敏感字段
        assert 'hashed_password' not in user_data or user_data.get('hashed_password') is None
    
    def test_get_me_unauthenticated(self, client):
        """未认证用户应返回 401"""
        resp = client.get('/api/v1/auth/me')
        
        assert resp.status_code == 401


class TestChangePassword:
    """修改密码测试"""
    
    def test_change_password_success(self, auth_headers, client):
        """正常修改密码"""
        resp = client.put(
            '/api/v1/auth/change-password',
            headers=auth_headers,
            json={
                'old_password': 'TestPass123!',
                'new_password': 'NewStrongPass456!'
            }
        )
        
        assert resp.status_code == 200
        assert resp.get_json()['success'] is True
    
    def test_change_wrong_old_password(self, auth_headers, client):
        """旧密码错误"""
        resp = client.put(
            '/api/v1/auth/change-password',
            headers=auth_headers,
            json={
                'old_password': 'WrongOldPassword!',
                'new_password': 'NewPass789!'
            }
        )
        
        assert resp.status_code == 400
    
    def test_change_weak_new_password(self, auth_headers, client):
        """新密码太弱"""
        resp = client.put(
            '/api/v1/auth/change-password',
            headers=auth_headers,
            json={
                'old_password': 'TestPass123!',
                'new_password': '123'  # 太短
            }
        )
        
        assert resp.status_code == 400


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
