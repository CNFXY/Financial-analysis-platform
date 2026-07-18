"""
FUND-OS RESTful API 路由层
遵循 REST 规范 + JWT 认证 + RBAC 权限控制
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from flask import Blueprint, request, jsonify, current_app, g
from werkzeug.security import check_password_hash

from core.auth import (
    generate_tokens, 
    verify_token,
    require_auth,
    require_role,
    rate_limit
)
from models.database import db_session
from models import User, FundInfo, Portfolio, Subscription

logger = logging.getLogger('fundos.api')

# ==================== 创建蓝图 ====================
api_bp = Blueprint('api', __name__, url_prefix='/api/v1')


# ==================== 认证模块 ====================
auth_bp = Blueprint('auth', __name__, url_prefix='/auth')


@auth_bp.route('/register', methods=['POST'])
def register():
    """用户注册"""
    data = request.get_json()
    
    # 验证必填字段
    required = ['username', 'email', 'password']
    for field in required:
        if not data or not data.get(field):
            return jsonify({
                'success': False,
                'error': f'Missing required field: {field}'
            }), 400
    
    # 检查用户名/邮箱是否已存在
    existing = User.query.filter(
        (User.username == data['username']) | (User.email == data['email'])
    ).first()
    
    if existing:
        return jsonify({
            'success': False,
            'error': 'Username or email already exists'
        }), 409
    
    try:
        user = User.create(
            username=data['username'],
            email=data['email'],
            password=data['password'],
            role='user'
        )
        
        tokens = generate_tokens(user.id)
        
        return jsonify({
            'success': True,
            'data': {
                'user': user.to_dict(),
                **tokens
            }
        }), 201
        
    except Exception as e:
        logger.error(f"Registration error: {e}")
        db_session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@auth_bp.route('/login', methods=['POST'])
def login():
    """用户登录"""
    data = request.get_json()
    
    if not data:
        return jsonify({
            'success': False,
            'error': 'Request body is required'
        }), 400
    
    username = data.get('username') or data.get('email')
    password = data.get('password')
    
    if not username or not password:
        return jsonify({
            'success': False,
            'error': 'Username and password are required'
        }), 400
    
    # 查找用户
    user = User.query.filter(
        (User.username == username) | (User.email == username)
    ).first()
    
    if not user or not user.check_password(password):
        return jsonify({
            'success': False,
            'error': 'Invalid credentials'
        }), 401
    
    if not user.is_active:
        return jsonify({
            'success': False,
            'error': 'Account is disabled'
        }), 403
    
    # 更新最后登录时间
    user.last_login = datetime.utcnow()
    db_session.commit()
    
    tokens = generate_tokens(user.id)
    
    return jsonify({
        'success': True,
        'data': {
            'user': user.to_dict(),
            **tokens
        }
    })


@auth_bp.route('/refresh', methods=['POST'])
def refresh_token():
    """刷新 Access Token"""
    data = request.get_json() or {}
    refresh_token = data.get('refresh_token')
    
    if not refresh_token:
        return jsonify({
            'success': False,
            'error': 'Refresh token is required'
        }), 400
    
    payload = verify_token(refresh_token, token_type='refresh')
    if not payload:
        return jsonify({
            'success': False,
            'error': 'Invalid or expired refresh token'
        }), 401
    
    new_tokens = generate_tokens(payload['sub'])
    
    return jsonify({
        'success': True,
        'data': new_tokens
    })


@auth_bp.route('/me', methods=['GET'])
@require_auth
def get_current_user():
    """获取当前用户信息"""
    return jsonify({
        'success': True,
        'data': g.current_user.to_dict(include_sensitive=True)
    })


@auth_bp.route('/change-password', methods=['POST'])
@require_auth
def change_password():
    """修改密码"""
    data = request.get_json()
    old_pwd = data.get('old_password')
    new_pwd = data.get('new_password')
    
    if not old_pwd or not new_pwd:
        return jsonify({
            'success': False,
            'error': 'Old and new passwords are required'
        }), 400
    
    user: User = g.current_user
    if not user.check_password(old_pwd):
        return jsonify({
            'success': False,
            'error': 'Current password is incorrect'
        }), 400
    
    if len(new_pwd) < 8:
        return jsonify({
            'success': False,
            'error': 'Password must be at least 8 characters'
        }), 400
    
    user.set_password(new_pwd)
    db_session.commit()
    
    return jsonify({'success': True, 'message': 'Password changed successfully'})


# 注册认证蓝图到 API
api_bp.register_blueprint(auth_bp)


# ==================== 基金数据模块 ====================
fund_bp = Blueprint('fund', __name__, url_prefix='/funds')


@fund_bp.route('', methods=['GET'])
@rate_limit(requests_per_minute=60)
def list_funds():
    """
    获取基金列表
    
    Query Params:
    - page: 页码（默认1）
    - per_page: 每页数量（默认20）
    - type: 类型 stock/bond/mixed/qdii
    - search: 搜索关键词（代码/名称）
    - sort_by: 排序字段
    - order: asc/desc
    """
    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 20, type=int), 100)
    fund_type = request.args.get('type')
    search = request.args.get('search')
    sort_by = request.args.get('sort_by', 'code')
    order = request.args.get('order', 'asc')
    
    query = FundInfo.query
    
    if fund_type:
        query = query.filter(FundInfo.fund_type == fund_type)
    
    if search:
        query = query.filter(
            (FundInfo.code.contains(search)) | 
            (FundInfo.name.contains(search))
        )
    
    # 排序
    sort_column = getattr(FundInfo, sort_by, None)
    if sort_column:
        query = query.order_by(sort_column.desc() if order == 'desc' else sort_column.asc())
    
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    
    return jsonify({
        'success': True,
        'data': {
            'items': [f.to_dict() for f in pagination.items],
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': pagination.total,
                'pages': pagination.pages
            }
        }
    })


@fund_bp.route('/<fund_code>', methods=['GET'])
def get_fund(fund_code: str):
    """
    获取基金详情
    
    Path: /api/v1/funds/{fund_code}
    
    Response: 基金基本信息 + 最近净值 + 估值
    """
    fund = FundInfo.query.filter(FundInfo.code == fund_code).first()
    
    if not fund:
        return jsonify({
            'success': False,
            'error': f'Fund {fund_code} not found'
        }), 404
    
    # 获取最近净值历史（最近30天）
    from models import FundNavHistory
    nav_history = FundNavHistory.query.filter(
        FundNavHistory.fund_code == fund_code
    ).order_by(FundNavHistory.date.desc()).limit(30).all()
    
    result = fund.to_dict()
    result['nav_history'] = [h.to_dict() for h in reversed(nav_history)]
    
    return jsonify({'success': True, 'data': result})


@fund_bp.route('/<fund_code>/estimate', methods=['GET'])
def get_fund_estimate(fund_code: str):
    """
    获取基金实时估值
    
    Path: /api/v1/funds/{fund_code}/estimate
    
    Response: 当前估算净值、涨跌幅、估值时间等
    """
    # TODO: 实际实现中从缓存或计算引擎获取实时估值
    # 这里返回模拟数据结构
    
    fund = FundInfo.query.filter(FundInfo.code == fund_code).first()
    if not fund:
        return jsonify({
            'success': False,
            'error': f'Fund {fund_code} not found'
        }), 404
    
    # 示例：从 Redis 获取最新估值
    from core.cache import cache_get
    cached_estimate = cache_get(f'estimate:{fund_code}')
    
    if cached_estimate:
        estimate_data = cached_estimate
    else:
        # 默认返回基础信息
        estimate_data = {
            "code": fund_code,
            "name": fund.name,
            "estimated_nav": None,
            "change_percent": None,
            "update_time": None,
            "status": "market_closed"
        }
    
    return jsonify({'success': True, 'data': estimate_data})


@fund_bp.route('/<fund_code>/nav-history', methods=['GET'])
def get_fund_nav_history(fund_code: str):
    """
    获取基金净值历史
    
    Query Params:
    - start_date: 开始日期 (YYYY-MM-DD)
    - end_date: 结束日期 (YYYY-MM-DD)
    """
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    from models import FundNavHistory
    query = FundNavHistory.query.filter(FundNavHistory.fund_code == fund_code)
    
    if start_date:
        query = query.filter(FundNavHistory.date >= start_date)
    if end_date:
        query = query.filter(FundNavHistory.date <= end_date)
    
    history = query.order_by(FundNavHistory.date.asc()).all()
    
    return jsonify({
        'success': True,
        'data': [h.to_dict() for h in history]
    })


@fund_bp.route('/search', methods=['GET'])
def search_funds():
    """
    搜索基金
    
    Query Param: q=搜索关键词
    """
    q = request.args.get('q', '').strip()
    
    if len(q) < 1:
        return jsonify({
            'success': False,
            'error': 'Search keyword must be at least 1 character'
        }), 400
    
    results = FundInfo.query.filter(
        (FundInfo.code.contains(q)) | (FundInfo.name.contains(q))
    ).limit(20).all()
    
    return jsonify({
        'success': True,
        'data': [f.to_dict() for f in results]
    })


api_bp.register_blueprint(fund_bp)


# ==================== 组合管理模块 ====================
portfolio_bp = Blueprint('portfolio', __name__, url_prefix='/portfolio')


@portfolio_bp.route('', methods=['GET'])
@require_auth
def list_portfolios():
    """获取用户的投资组合列表"""
    portfolios = Portfolio.query.filter(Portfolio.user_id == g.user_id).all()
    
    return jsonify({
        'success': True,
        'data': [p.to_dict() for p in portfolios]
    })


@portfolio_bp.route('', methods=['POST'])
@require_auth
def create_portfolio():
    """创建新组合"""
    data = request.get_json()
    
    name = data.get('name')
    if not name:
        return jsonify({
            'success': False,
            'error': 'Portfolio name is required'
        }), 400
    
    portfolio = Portfolio.create(
        user_id=g.user_id,
        name=name,
        description=data.get('description'),
        is_default=data.get('is_default', False)
    )
    
    return jsonify({
        'success': True,
        'data': portfolio.to_dict()
    }), 201


@portfolio_bp.route('/<int:portfolio_id>', methods=['GET'])
@require_auth
def get_portfolio(portfolio_id: int):
    """获取组合详情（含持仓和收益统计）"""
    portfolio = Portfolio.query.filter(
        Portfolio.id == portfolio_id,
        Portfolio.user_id == g.user_id
    ).first()
    
    if not portfolio:
        return jsonify({
            'success': False,
            'error': 'Portfolio not found'
        }), 404
    
    return jsonify({
        'success': True,
        'data': portfolio.to_dict(detailed=True)
    })


@portfolio_bp.route('/<int:portfolio_id>', methods=['PUT'])
@require_auth
def update_portfolio(portfolio_id: int):
    """更新组合信息"""
    portfolio = Portfolio.query.filter(
        Portfolio.id == portfolio_id,
        Portfolio.user_id == g.user_id
    ).first()
    
    if not portfolio:
        return jsonify({
            'success': False,
            'error': 'Portfolio not found'
        }, 404)
    
    data = request.get_json()
    
    if 'name' in data:
        portfolio.name = data['name']
    if 'description' in data:
        portfolio.description = data['description']
    if 'is_default' in data:
        portfolio.is_default = data['is_default']
    
    db_session.commit()
    
    return jsonify({
        'success': True,
        'data': portfolio.to_dict()
    })


@portfolio_bp.route('/<int:portfolio_id>', methods=['DELETE'])
@require_auth
def delete_portfolio(portfolio_id: int):
    """删除组合"""
    portfolio = Portfolio.query.filter(
        Portfolio.id == portfolio_id,
        Portfolio.user_id == g.user_id
    ).first()
    
    if not portfolio:
        return jsonify({
            'success': False,
            'error': 'Portfolio not found'
        }), 404
    
    db_session.delete(portfolio)
    db_session.commit()
    
    return jsonify({'success': True})


@portfolio_bp.route('/<int:portfolio_id>/holdings', methods=['POST'])
@require_auth
def add_holding(portfolio_id: int):
    """添加持仓"""
    portfolio = Portfolio.query.filter(
        Portfolio.id == portfolio_id,
        Portfolio.user_id == g.user_id
    ).first()
    
    if not portfolio:
        return jsonify({
            'success': False,
            'error': 'Portfolio not found'
        }), 404
    
    data = request.get_json()
    
    holding = portfolio.add_holding(
        fund_code=data.get('fund_code'),
        shares=data.get('shares'),
        cost_price=data.get('cost_price'),
        buy_date=data.get('buy_date')
    )
    
    return jsonify({
        'success': True,
        'data': holding.to_dict() if holding else None
    }), 201


@portfolio_bp.route('/summary', methods=['GET'])
@require_auth
def get_portfolio_summary():
    """获取所有组合的汇总信息（总资产、总收益）"""
    portfolios = Portfolio.query.filter(Portfolio.user_id == g.user_id).all()
    
    total_value = sum(p.total_value or 0 for p in portfolios)
    total_cost = sum(p.total_cost or 0 for p in portfolios)
    total_pnl = total_value - total_cost
    total_pnl_pct = (total_pnl / total_cost * 100) if total_cost > 0 else 0
    
    return jsonify({
        'success': True,
        'data': {
            'total_portfolios': len(portfolios),
            'total_holdings': sum(len(p.holdings) for p in portfolios),
            'total_value': round(total_value, 2),
            'total_cost': round(total_cost, 2),
            'total_pnl': round(total_pnl, 2),
            'total_pnl_percent': round(total_pnl_pct, 2),
            'portfolios': [
                {
                    'id': p.id,
                    'name': p.name,
                    'value': round(p.total_value or 0, 2),
                    'pnl': round((p.total_value or 0) - (p.total_cost or 0), 2)
                } for p in portfolios
            ]
        }
    })


api_bp.register_blueprint(portfolio_bp)


# ==================== 实时行情模块 ====================
realtime_bp = Blueprint('realtime', __name__, url_prefix='/realtime')


@realtime_bp.route('/quotes/<fund_codes>', methods=['GET'])
@rate_limit(requests_per_minute=120)
def get_realtime_quotes(fund_codes: str):
    """
    批量获取实时行情
    
    Path: /api/v1/realtime/quotes/{codes}
    
    codes 格式: 用逗号分隔，如 "000001,000002,600036"
    """
    codes = [c.strip().upper() for c in fund_codes.split(',') if c.strip()]
    
    if len(codes) > 50:
        return jsonify({
            'success': False,
            'error': 'Maximum 50 codes per request'
        }), 400
    
    # TODO: 实际实现中从 Tushare/Yahoo Finance API 或 WebSocket 缓存获取
    quotes = []
    for code in codes:
        fund = FundInfo.query.filter(FundInfo.code == code).first()
        quotes.append({
            'code': code,
            'name': fund.name if fund else 'Unknown',
            'price': None,      # 实时价格
            'change': None,      # 涨跌额
            'change_pct': None,   # 涨跌幅
            'volume': None,       # 成交量
            'high': None,         # 最高
            'low': None,          # 最低
            'open': None,         # 开盘
            'prev_close': None,   # 昨收
            'update_time': datetime.now().isoformat(),
            'status': 'trading'   # trading/suspended/closed
        })
    
    return jsonify({
        'success': True,
        'data': {
            'quotes': quotes,
            'timestamp': datetime.now().isoformat(),
            'source': 'cache'
        }
    })


@realtime_bp.route('/market-status', methods=['GET'])
def get_market_status():
    """获取市场状态（开盘/休市/节假日等）"""
    now = datetime.now()
    
    # 简单判断逻辑（实际应使用交易日历API）
    weekday = now.weekday()
    hour = now.hour
    minute = now.minute
    
    if weekday >= 5:  # 周末
        status = 'closed'
        next_open = now + timedelta(days=(7 - weekday))
    elif hour < 9 or (hour == 9 and minute < 30):
        status = 'pre_market'
    elif 9 <= hour < 11 or (hour == 11 and minute < 30) or (13 <= hour < 15):
        status = 'trading'
    elif 11 <= hour < 13:
        status = 'lunch_break'
    elif hour >= 15:
        status = 'closed'
    else:
        status = 'unknown'
    
    return jsonify({
        'success': True,
        'data': {
            'status': status,
            'current_time': now.isoformat(),
            'market_name': 'A股',
            'open_time': '09:30',
            'close_time': '15:00',
            'lunch_start': '11:30',
            'lunch_end': '13:00'
        }
    })


@realtime_bp.route('/top-gainers', methods=['GET'])
def get_top_gainers():
    """获取涨幅榜 TOP N"""
    limit = min(request.args.get('limit', 10, type=int), 50)
    
    # TODO: 从实时数据源查询
    return jsonify({
        'success': True,
        'data': {
            'items': [],
            'updated_at': datetime.now().isoformat()
        },
        'message': 'Real-time data source integration pending'
    })


@realtime_bp.route('/top-losers', methods=['GET'])
def get_top_losers():
    """获取跌幅榜 TOP N"""
    limit = min(request.args.get('limit', 10, type=int), 50)
    
    return jsonify({
        'success': True,
        'data': {
            'items': [],
            'updated_at': datetime.now().isoformat()
        },
        'message': 'Real-time data source integration pending'
    })


api_bp.register_blueprint(realtime_bp)


# ==================== 报告模块 ====================
report_bp = Blueprint('report', __name__, url_prefix='/reports')


@report_bp.route('', methods=['GET'])
@require_auth
def list_reports():
    """获取报告列表"""
    reports = Report.query.filter(Report.user_id == g.user_id).order_by(
        Report.created_at.desc()
    ).all()
    
    return jsonify({
        'success': True,
        'data': [r.to_dict() for r in reports]
    })


@report_bp.route('/generate', methods=['POST'])
@require_auth
def generate_report():
    """生成新的分析报告"""
    data = request.get_json()
    report_type = data.get('type', 'monthly')  # daily/weekly/monthly/custom
    portfolio_ids = data.get('portfolio_ids', [])
    date_range = data.get('date_range', {})
    
    # TODO: 实现报告生成逻辑
    report = {
        'id': None,
        'type': report_type,
        'status': 'generating',
        'created_at': datetime.now().isoformat(),
        'message': 'Report generation engine integration pending'
    }
    
    return jsonify({
        'success': True,
        'data': report
    }, 202)


@report_bp.route('/<int:report_id>', methods=['GET'])
@require_auth
def get_report(report_id: int):
    """获取报告详情"""
    from models import Report
    report = Report.query.filter(
        Report.id == report_id,
        Report.user_id == g.user_id
    ).first()
    
    if not report:
        return jsonify({
            'success': False,
            'error': 'Report not found'
        }), 404
    
    return jsonify({'success': True, 'data': report.to_dict()})


@report_bp.route('/<int:report_id>/export', methods=['GET'])
@require_auth
def export_report(report_id: int):
    """导出报告（PDF/Excel）"""
    format_type = request.args.get('format', 'pdf')
    
    if format_type not in ['pdf', 'excel']:
        return jsonify({
            'success': False,
            'error': 'Format must be pdf or excel'
        }), 400
    
    # TODO: 实现导出功能
    return jsonify({
        'success': False,
        'message': 'Export functionality pending implementation'
    }), 501


api_bp.register_blueprint(report_bp)


# ==================== 管理员模块 ====================
admin_bp = Blueprint('admin', __name__, url_prefix='/admin')


@admin_bp.route('/users', methods=['GET'])
@require_role(['admin'])
def admin_list_users():
    """管理员：获取用户列表"""
    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 20, type=int), 100)
    
    users = User.query.order_by(User.created_at.desc()).paginate(
        page=page, per_page=per_page
    )
    
    return jsonify({
        'success': True,
        'data': {
            'items': [u.to_dict() for u in users.items],
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': users.total,
                'pages': users.pages
            }
        }
    })


@admin_bp.route('/users/<int:user_id>', methods=['PUT'])
@require_role(['admin'])
def admin_update_user(user_id: int):
    """管理员：更新用户状态"""
    user = User.query.get(user_id)
    if not user:
        return jsonify({
            'success': False,
            'error': 'User not found'
        }), 404
    
    data = request.get_json()
    
    if 'role' in data and data['role'] in ['admin', 'user', 'viewer']:
        user.role = data['role']
    if 'is_active' in data:
        user.is_active = data['is_active']
    
    db_session.commit()
    
    return jsonify({'success': True, 'data': user.to_dict()})


@admin_bp.route('/stats', methods=['GET'])
@require_role(['admin'])
def admin_get_stats():
    """管理员：获取系统统计数据"""
    stats = {
        'users': {
            'total': User.query.count(),
            'active_today': User.query.filter(User.last_login >= datetime.now() - timedelta(days=1)).count()
        },
        'funds': {
            'total': FundInfo.query.count(),
            'types': {}  # TODO: 按类型分组统计
        },
        'portfolios': Portfolio.query.count(),
        'system': {
            'version': current_app.config.get('APP_VERSION', '5.0.0'),
            'uptime': 'TODO',
            'database_status': 'connected'
        }
    }
    
    return jsonify({'success': True, 'data': stats})


@admin_bp.route('/config', methods=['GET', 'PUT'])
@require_role(['admin'])
def admin_config():
    """管理员：系统配置管理"""
    from models import SystemConfig
    
    if request.method == 'GET':
        configs = SystemConfig.query.all()
        return jsonify({
            'success': True,
            'data': {c.key: c.value for c in configs}
        })
    
    else:  # PUT
        data = request.get_json()
        updates = []
        for key, value in data.items():
            config = SystemConfig.query.filter(SystemConfig.key == key).first()
            if config:
                config.value = value
            else:
                config = SystemConfig(key=key, value=value)
                db_session.add(config)
            updates.append(key)
        
        db_session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Updated {len(updates)} config items'
        })


api_bp.register_blueprint(admin_bp)


# ==================== 全局错误处理 ====================


@api_bp.errorhandler(400)
def bad_request(error):
    return jsonify({
        'success': False,
        'error': 'Bad request',
        'details': str(error)
    }), 400


@api_bp.errorhandler(401)
def unauthorized(error):
    return jsonify({
        'success': False,
        'error': 'Authentication required',
        'code': 'AUTH_REQUIRED'
    }), 401


@api_bp.errorhandler(403)
def forbidden(error):
    return jsonify({
        'success': False,
        'error': 'Insufficient permissions',
        'code': 'FORBIDDEN'
    }), 403


@api_bp.errorhandler(404)
def not_found(error):
    return jsonify({
        'success': False,
        'error': 'Resource not found'
    }), 404


@api_bp.errorhandler(429)
def rate_limited(error):
    return jsonify({
        'success': False,
        'error': 'Too many requests, please slow down',
        'code': 'RATE_LIMITED'
    }), 429


@api_bp.errorhandler(500)
def internal_error(error):
    logger.exception("Internal server error")
    db_session.rollback()
    return jsonify({
        'success': False,
        'error': 'Internal server error',
        'code': 'INTERNAL_ERROR'
    }), 500


# 注册所有蓝图到 Flask app 的函数
def register_blueprints(app):
    """在应用工厂中注册所有 API 蓝图"""
    app.register_blueprint(api_bp)
    logger.info("All API blueprints registered successfully")
