"""
FUND-OS 基金数据 API 测试
覆盖: 基金列表/搜索/详情/估值/净值历史
"""

import pytest
from datetime import datetime, timedelta


class TestFundListAPI:
    """基金列表接口测试"""
    
    def test_list_funds_empty(self, client):
        """空数据库返回空列表"""
        resp = client.get('/api/v1/funds')
        
        data = resp.get_json()
        assert resp.status_code == 200
        assert data['success'] is True
        assert data['data']['items'] == []
        assert data['data']['pagination']['total'] == 0
    
    def test_list_funds_with_data(self, client, db_session):
        """有数据时返回正确分页结果"""
        from models import FundInfo
        
        # 创建测试数据
        for i in range(25):  # 创建 25 条，分 2 页
            fund = FundInfo(
                code=f'{i:06d}',
                name=f'测试基金{i}',
                fund_type='mixed',
                nav=1.0000 + i * 0.01,
                nav_date=datetime.now().date()
            )
            db_session.add(fund)
        db_session.commit()
        
        # 第一页
        resp = client.get('/api/v1/funds?page=1&per_page=10')
        data = resp.get_json()
        
        assert len(data['data']['items']) == 10
        assert data['data']['pagination']['page'] == 1
        assert data['data']['pagination']['total'] == 25
        assert data['data']['pagination']['pages'] == 3
    
    def test_list_funds_filter_by_type(self, client, db_session):
        """按类型筛选"""
        from models import FundInfo
        
        for ft in ['stock', 'bond', 'mixed']:
            for i in range(5):
                db_session.add(FundInfo(
                    code=f'{ft}{i:03d}',
                    name=f'{ft}基金{i}',
                    fund_type=ft,
                    nav=1.0
                ))
        db_session.commit()
        
        resp = client.get('/api/v1/funds?type=bond')
        data = resp.get_json()
        
        assert all(f['fund_type'] == 'bond' for f in data['data']['items'])
        assert len(data['data']['items']) == 5
    
    def test_list_funds_search(self, client, db_session):
        """搜索功能"""
        from models import FundInfo
        
        db_session.add(FundInfo(code='000001', name='华夏成长混合'))
        db_session.add(FundInfo(code='000002', name='易方达蓝筹精选'))
        db_session.add(FundInfo(code='000003', name='招商中证白酒'))
        db_session.commit()
        
        # 按名称搜索
        resp = client.get('/api/v1/funds?search=白酒')
        data = resp.get_json()
        
        assert len(data['data']['items']) == 1
        assert '白酒' in data['data']['items'][0]['name']
    
    def test_list_funds_pagination_limits(self, client, db_session):
        """分页限制：per_page 最大值"""
        from models import FundInfo
        for i in range(200):
            db_session.add(FundInfo(code=f't{i:04d}', name=f'基金{i}', fund_type='stock'))
        db_session.commit()
        
        # 请求超过上限的 per_page
        resp = client.get('/api/v1/funds?per_page=1000')
        data = resp.get_json()
        
        # 应被截断到最大值（100）
        assert len(data['data']['items']) <= 100


class TestFundDetailAPI:
    """基金详情接口测试"""
    
    @pytest.fixture(autouse=True)
    def setup_fund(self, db_session):
        """创建测试基金"""
        from models import FundInfo, FundNavHistory
        
        self.fund = FundInfo(
            code='110022',
            name='易方达消费行业股票',
            fund_type='stock',
            nav=3.4567,
            nav_date=datetime.now().date(),
            manager='萧楠',
            company='易方达基金'
        )
        db_session.add(self.fund)
        
        # 添加净值历史
        for i in range(30):
            nav_h = FundNavHistory(
                fund_code='110022',
                date=(datetime.now() - timedelta(days=i)).date(),
                unit_nav=3.4 + (i % 10) / 100,
                daily_change_pct=((i % 7) - 3) * 0.2
            )
            db_session.add(nav_h)
        
        db_session.commit()
    
    def test_get_existing_fund(self, client):
        """获取已存在的基金"""
        resp = client.get('/api/v1/funds/110022')
        data = resp.get_json()
        
        assert resp.status_code == 200
        assert data['success'] is True
        assert data['data']['code'] == '110022'
        assert data['data']['name'] == '易方达消费行业股票'
        assert len(data['data'].get('nav_history', [])) > 0
    
    def test_get_nonexistent_fund(self, client):
        """获取不存在的基金"""
        resp = client.get('/api/v1/funds/999999')
        
        assert resp.status_code == 404


class TestFundEstimateAPI:
    """基金估值接口测试"""
    
    def test_get_estimate_for_existing_fund(self, client, db_session):
        """获取已有基金的估值"""
        from models import FundInfo
        
        db_session.add(FundInfo(code='161725', name='招商中证白酒指数'))
        db_session.commit()
        
        resp = client.get('/api/v1/funds/161725/estimate')
        data = resp.get_json()
        
        assert resp.status_code == 200
        assert data['success'] is True
        assert data['data']['code'] == '161725'
    
    def test_get_estimate_nonexistent_fund(self, client):
        """获取不存在基金的估值"""
        resp = client.get('/api/v1/funds/000000/estimate')
        
        assert resp.status_code == 404


class TestFundNavHistoryAPI:
    """净值历史接口测试"""
    
    @pytest.fixture(autouse=True)
    def setup_nav_data(self, db_session):
        """创建净值历史数据"""
        from models import FundInfo, FundNavHistory
        
        self.fund = FundInfo(code='000001', name='测试基金A', fund_type='mixed')
        db_session.add(self.fund)
        
        base_date = datetime(2024, 1, 1)
        for i in range(60):  # 60 天历史
            date = (base_date + timedelta(days=i)).date()
            if date.weekday() < 5:  # 工作日
                nav_h = FundNavHistory(
                    fund_code='000001',
                    date=date,
                    unit_nav=1.20 + i * 0.002,
                    accumulated_nav=1.80 + i * 0.003,
                    daily_change_pct=0.15 + (i % 5) * 0.05
                )
                db_session.add(nav_h)
        
        db_session.commit()
    
    def test_nav_history_default_range(self, client):
        """默认日期范围"""
        resp = client.get('/api/v1/funds/000001/nav-history')
        data = resp.get_json()
        
        assert resp.status_code == 200
        assert isinstance(data['data'], list)
        # 应该有多条记录
        assert len(data['data']) > 0
    
    def test_nav_history_custom_range(self, client):
        """自定义日期范围"""
        start = '2024-02-01'
        end = '2024-02-29'
        
        resp = client.get(f'/api/v1/funds/000001/nav-history?start_date={start}&end_date={end}')
        data = resp.get_json()
        
        assert resp.status_code == 200
        for item in data['data']:
            assert item['date'] >= start
            assert item['date'] <= end


class TestFundSearchAPI:
    """基金搜索接口测试"""
    
    def test_search_by_code(self, client, db_session):
        """按代码搜索"""
        from models import FundInfo
        db_session.add(FundInfo(code='005827', name='易方达沪深300ETF联接'))
        db_session.commit()
        
        resp = client.get('/api/v1/funds/search?q=005827')
        data = resp.get_json()
        
        assert len(data['data']) == 1
        assert data['data'][0]['code'] == '005827'
    
    def test_search_by_name(self, client, db_session):
        """按名称搜索"""
        from models import FundInfo
        db_session.add(FundInfo(code='001234', name='南方医药保健灵活配置混合'))
        db_session.commit()
        
        resp = client.get('/api/v1/funds/search?q=医药')
        data = resp.get_json()
        
        assert len(data['data']) >= 1
        assert '医药' in data['data'][0]['name']
    
    def test_search_empty_query(self, client):
        """空搜索关键词应报错"""
        resp = client.get('/api/v1/funds/search?q=')
        
        assert resp.status_code == 400
    
    def test_search_no_results(self, client):
        """无匹配结果"""
        resp = client.get('/api/v1/funds/search?q=不存在的基金xyz123')
        data = resp.get_json()
        
        assert resp.status_code == 200
        assert len(data['data']) == 0


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
