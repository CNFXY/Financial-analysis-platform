"""
FUND-OS 组合管理 API 测试（续）
覆盖: 汇总计算/权限控制
"""

import pytest


class TestPortfolioSummary:
    """组合汇总信息测试"""
    
    @pytest.fixture(autouse=True)
    def setup(self, auth_headers, db_session, client):
        self.auth = auth_headers
        self.db = db_session
        self.client = client
        self.user_id = 1
    
    def test_summary_empty(self):
        """空账户汇总"""
        resp = self.client.get('/api/v1/portfolio/summary', headers=self.auth)
        data = resp.get_json()
        
        assert resp.status_code == 200
        assert data['data']['total_portfolios'] == 0
        assert data['data']['total_value'] == 0
    
    def test_summary_with_data(self):
        """有数据时的汇总"""
        from models import Portfolio
        
        # 创建两个组合，每个带一些持仓
        for i in range(2):
            portfolio = Portfolio(
                user_id=self.user_id,
                name=f'汇总组合{i}',
                total_value=10000 * (i + 1),
                total_cost=9000 * (i + 1)
            )
            self.db.add(portfolio)
        self.db.commit()
        
        resp = self.client.get('/api/v1/portfolio/summary', headers=self.auth)
        data = resp.get_json()
        
        assert data['success'] is True
        summary = data['data']
        assert summary['total_portfolios'] == 2
        # 总价值 = 10000 + 20000 = 30000
        assert summary['total_value'] > 0
        assert 'total_pnl' in summary
        assert 'total_pnl_percent' in summary


class TestPortfolioPermissions:
    """组合权限控制测试"""
    
    @pytest.fixture(autouse=True)
    def setup(self, db_session):
        self.db = db_session
        
        # 用户 A 的组合（conftest 中注册的用户）
        from models import Portfolio
        self.portfolio_a = Portfolio(user_id=1, name='用户A的组合')
        self.db.add(self.portfolio_a)
        
        # 用户 B 的组合
        user_b_portfolio = Portfolio(user_id=999, name='用户B的组合')
        self.db.add(user_b_portfolio)
        self.db.commit()
    
    def test_user_can_access_own_portfolio(self, auth_headers, client):
        """用户可以访问自己的组合"""
        resp = client.get(
            f'/api/v1/portfolio/{self.portfolio_a.id}',
            headers=auth_headers
        )
        
        assert resp.status_code == 200
    
    def test_user_cannot_access_others_portfolio(self, auth_headers, client):
        """用户不能访问他人的组合"""
        resp = client.get(
            '/api/v1/portfolio/99999',  # 假设 id=999 是用户B的
            headers=auth_headers
        )
        
        assert resp.status_code == 404
    
    def test_unauthenticated_cannot_access(self, client):
        """未认证用户不能访问组合"""
        resp = client.get(f'/api/v1/portfolio/{self.portfolio_a.id}')
        
        assert resp.status_code == 401
    
    def test_unauthenticated_cannot_create(self, client):
        """未认证用户不能创建组合"""
        resp = client.post('/api/v1/portfolio', json={'name': '未认证创建'})
        
        assert resp.status_code == 401


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
