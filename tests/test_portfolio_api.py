"""
FUND-OS 组合管理 API 测试
覆盖: CRUD操作/持仓管理/收益计算
"""

import pytest
from datetime import datetime, date


class TestPortfolioCRUD:
    """组合增删改查测试"""
    
    @pytest.fixture(autouse=True)
    def setup(self, auth_headers, db_session):
        self.auth = auth_headers
        self.db = db_session
        self.user_id = 1  # conftest 中注册的用户
    
    def test_create_portfolio_success(self, client):
        """创建组合成功"""
        resp = client.post(
            '/api/v1/portfolio',
            headers=self.auth,
            json={
                'name': '我的第一组合',
                'description': '用于测试的组合'
            }
        )
        
        data = resp.get_json()
        assert resp.status_code == 201
        assert data['success'] is True
        assert data['data']['name'] == '我的第一组合'
    
    def test_create_portfolio_missing_name(self, client):
        """缺少名称应报错"""
        resp = client.post(
            '/api/v1/portfolio',
            headers=self.auth,
            json={'description': '没有名称'}
        )
        
        assert resp.status_code == 400
    
    def test_list_portfolios_empty(self, client):
        """空组合列表"""
        resp = client.get('/api/v1/portfolio', headers=self.auth)
        
        data = resp.get_json()
        assert resp.status_code == 200
        assert data['data'] == []
    
    def test_list_portfolios_with_data(self, client, db_session):
        """有数据时的列表"""
        from models import Portfolio
        
        # 创建多个组合
        for i in range(3):
            portfolio = Portfolio(
                user_id=self.user_id,
                name=f'组合{i+1}',
                is_default=(i == 0)
            )
            self.db.add(portfolio)
        self.db.commit()
        
        resp = client.get('/api/v1/portfolio', headers=self.auth)
        data = resp.get_json()
        
        assert len(data['data']) == 3
    
    def test_get_portfolio_detail(self, client, db_session):
        """获取组合详情"""
        from models import Portfolio
        
        portfolio = Portfolio(user_id=self.user_id, name='详细组合')
        self.db.add(portfolio)
        self.db.commit()
        
        resp = client.get(f'/api/v1/portfolio/{portfolio.id}', headers=self.auth)
        data = resp.get_json()
        
        assert resp.status_code == 200
        assert data['data']['name'] == '详细组合'
    
    def test_get_nonexistent_portfolio(self, client):
        """获取不存在的组合"""
        resp = client.get('/api/v1/portfolio/99999', headers=self.auth)
        
        assert resp.status_code == 404
    
    def test_update_portfolio(self, client, db_session):
        """更新组合信息"""
        from models import Portfolio
        
        portfolio = Portfolio(user_id=self.user_id, name='原始名称')
        self.db.add(portfolio)
        self.db.commit()
        
        resp = client.put(
            f'/api/v1/portfolio/{portfolio.id}',
            headers=self.auth,
            json={
                'name': '新名称',
                'description': '更新后的描述'
            }
        )
        
        data = resp.get_json()
        assert resp.status_code == 200
        assert data['data']['name'] == '新名称'
    
    def test_delete_portfolio(self, client, db_session):
        """删除组合"""
        from models import Portfolio
        
        portfolio = Portfolio(user_id=self.user_id, name='待删除')
        self.db.add(portfolio)
        self.db.commit()
        
        resp = client.delete(f'/api/v1/portfolio/{portfolio.id}', headers=self.auth)
        
        assert resp.status_code == 200
        
        # 确认已删除
        get_resp = client.get(f'/api/v1/portfolio/{portfolio.id}', headers=self.auth)
        assert get_resp.status_code == 404


class TestPortfolioHoldings:
    """持仓管理测试"""
    
    @pytest.fixture(autouse=True)
    def setup(self, auth_headers, db_session, client):
        self.auth = auth_headers
        self.db = db_session
        self.client = client
        self.user_id = 1
        
        # 创建一个组合用于测试
        from models import Portfolio
        self.portfolio = Portfolio(user_id=self.user_id, name='持仓测试组合')
        self.db.add(self.portfolio)
        self.db.commit()
    
    def test_add_holding(self):
        """添加持仓成功"""
        resp = self.client.post(
            f'/api/v1/portfolio/{self.portfolio.id}/holdings',
            headers=self.auth,
            json={
                'fund_code': '110022',
                'shares': 1000.0,
                'cost_price': 2.5000,
                'buy_date': '2024-01-15'
            }
        )
        
        assert resp.status_code == 201
        data = resp.get_json()
        assert data['success'] is True
    
    def test_add_holding_to_nonexistent_portfolio(self):
        """向不存在的组合添加持仓"""
        resp = self.client.post(
            '/api/v1/portfolio/99999/holdings',
            headers=self.auth,
            json={'fund_code': '000001', 'shares': 100}
        )
        
        assert resp.status_code == 404
    
    def test_multiple_holdings(self):
        """添加多个持仓"""
        funds = ['000001', '000002', '110022', '161725']
        
        for code in funds:
            resp = self.client.post(
                f'/api/v1/portfolio/{self.portfolio.id}/holdings',
                headers=self.auth,
                json={
                    'fund_code': code,
                    'shares': float(hash(code) % 10000) / 10,
                    'cost_price': 1.5 + (hash(code) % 50) / 100
                }
            )
            assert resp.status_code == 201
        
        # 验证组合中的持仓数量
        resp = self.client.get(f'/api/v1/portfolio/{self.portfolio.id}', headers=self.auth)
        data = resp.get_json()
        
        # 详细视图应包含 holdings
        if 'holdings' in data['data']:
            assert len(data['data']['holdings']) == 4
