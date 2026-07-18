"""
FUND-OS 管理员 API 测试
覆盖: 用户管理/系统配置/权限控制
"""

import pytest


class TestAdminUserManagement:
    """管理员：用户管理测试"""
    
    @pytest.fixture(autouse=True)
    def setup(self, admin_auth_headers, db_session, client):
        self.auth = admin_auth_headers
        self.db = db_session
        self.client = client
    
    def test_admin_list_users(self):
        """管理员可以查看用户列表"""
        resp = self.client.get('/api/v1/admin/users', headers=self.auth)
        
        data = resp.get_json()
        assert resp.status_code == 200
        assert 'data' in data
        assert 'items' in data['data']
        assert 'pagination' in data['data']
    
    def test_admin_update_user_role(self, db_session, client):
        """管理员可以修改用户角色"""
        from models import User
        
        # 创建一个普通用户
        user = User.create(
            username='role_target',
            email='role@test.com',
            password='Pass123!'
        )
        self.db.commit()
        
        resp = self.client.put(
            f'/api/v1/admin/users/{user.id}',
            headers=self.auth,
            json={'role': 'admin'}
        )
        
        data = resp.get_json()
        assert resp.status_code == 200
        assert data['data']['role'] == 'admin'
    
    def test_admin_disable_user(self, db_session, client):
        """管理员可以禁用用户"""
        from models import User
        
        user = User.create(
            username='disable_me',
            email='disable@test.com',
            password='Pass123!'
        )
        self.db.commit()
        
        resp = self.client.put(
            f'/api/v1/admin/users/{user.id}',
            headers=self.auth,
            json={'is_active': False}
        )
        
        data = resp.get_json()
        assert resp.status_code == 200
    
    def test_regular_user_cannot_access_admin(self, auth_headers, client):
        """普通用户不能访问管理员接口"""
        resp = client.get('/api/v1/admin/users', headers=auth_headers)
        
        assert resp.status_code == 403
    
    def test_unauthenticated_cannot_access_admin(self, client):
        """未认证用户不能访问管理员接口"""
        resp = client.get('/api/v1/admin/users')
        
        assert resp.status_code == 401


class TestAdminSystemConfig:
    """管理员：系统配置测试"""
    
    @pytest.fixture(autouse=True)
    def setup(self, admin_auth_headers, client):
        self.auth = admin_auth_headers
        self.client = client
    
    def test_get_config(self):
        """获取系统配置"""
        resp = self.client.get('/api/v1/admin/config', headers=self.auth)
        
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data.get('data'), dict)
    
    def test_update_config(self):
        """更新系统配置"""
        resp = self.client.put(
            '/api/v1/admin/config',
            headers=self.auth,
            json={
                'site_name': 'FUND-OS 测试站',
                'maintenance_mode': False,
                'max_funds_per_portfolio': 50
            }
        )
        
        data = resp.get_json()
        assert resp.status_code == 200
        assert data['success'] is True


class TestAdminStats:
    """管理员：系统统计测试"""
    
    @pytest.fixture(autouse=True)
    def setup(self, admin_auth_headers, client):
        self.auth = admin_auth_headers
        self.client = client
    
    def test_get_system_stats(self):
        """获取系统统计信息"""
        resp = self.client.get('/api/v1/admin/stats', headers=self.auth)
        
        data = resp.get_json()
        assert resp.status_code == 200
        stats = data['data']
        
        # 验证返回的统计结构
        assert 'users' in stats
        assert 'funds' in stats
        assert 'system' in stats
        assert isinstance(stats['users']['total'], int)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
