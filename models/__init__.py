"""
FUND-OS 数据模型层 v5.0
基于 SQLAlchemy ORM 的完整数据模型定义
支持 SQLite（开发） / PostgreSQL（生产）
"""

from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Float, Boolean,
    DateTime, Text, JSON, ForeignKey, Index, UniqueConstraint,
    BigInteger, Date,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


# ==================== 用户与认证 ====================
class User(Base):
    """用户表

    计费模型（用户属于租户，订阅可下钻到用户或租户）：
    - tenant_id 为用户所属租户；为 None 时视为个人租户（tenant_id == user.id）
    - 订阅（billing_subscriptions）按 scope_type/scope_id 落在 用户 或 租户 上
    """
    __tablename__ = 'users'

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    username = Column(String(64), unique=True, nullable=False, index=True)
    email = Column(String(128), unique=True, nullable=False, index=True)
    password_hash = Column(String(256), nullable=False)
    role = Column(String(16), default='user')  # admin / user / viewer
    tenant_id = Column(String(36), index=True)  # 所属租户（可为空）
    avatar_url = Column(String(512))
    is_active = Column(Boolean, default=True)
    last_login = Column(DateTime)

    # 关联
    portfolios = relationship('Portfolio', back_populates='owner', lazy='dynamic')
    subscriptions = relationship('Subscription', back_populates='user', uselist=False)

    def set_password(self, password: str) -> None:
        from fund_estimation_system.core.auth import hash_password
        self.password_hash = hash_password(password)

    def check_password(self, password: str) -> bool:
        from fund_estimation_system.core.auth import verify_password
        return verify_password(password, self.password_hash)

    def to_dict(self, include_sensitive: bool = False) -> dict:
        d = {
            'id': self.id,
            'username': self.username,
            'email': self.email,
            'role': self.role,
            'tenant_id': self.tenant_id,
            'is_active': self.is_active,
            'last_login': self.last_login.isoformat() if self.last_login else None,
        }
        if include_sensitive:
            d['avatar_url'] = self.avatar_url
        return d

    @classmethod
    def create(cls, username, email, password, role='user', tenant_id=None,
               avatar_url=None, is_active=True):
        u = cls(username=username, email=email, role=role,
                tenant_id=tenant_id, avatar_url=avatar_url, is_active=is_active)
        u.set_password(password)
        return u


class Subscription(Base):
    """订阅/套餐表（通用占位，实际商业化订阅见 billing_subscriptions）"""
    __tablename__ = 'subscriptions'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(36), ForeignKey('users.id'), unique=True)
    plan = Column(String(32), default='free')  # free / basic / pro / enterprise
    status = Column(String(16), default='active')
    started_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime)
    quota_used = Column(Integer, default=0)
    quota_limit = Column(Integer, default=100)  # 每日 API 调用限制

    user = relationship('User', back_populates='subscriptions')


# ==================== 基金数据 ====================
class FundInfo(Base):
    """基金基本信息"""
    __tablename__ = 'fund_info'

    code = Column(String(12), primary_key=True)
    name = Column(String(128), nullable=False)
    type = Column(String(32))  # 股票型 / 债券型 / 混合型 / 货币型 / ETF / LOF
    manager = Column(String(64))  # 基金经理
    company = Column(String(128))  # 基金公司
    establish_date = Column(Date)
    nav_unit = Column(Float)  # 单位净值
    nav_acc = Column(Float)  # 累计净值
    nav_date = Column(Date)
    change_pct_day = Column(Float)  # 日涨跌%
    total_assets = Column(Float)  # 资产规模 (亿)
    fee_buy = Column(Float)  # 申购费率
    fee_sell = Column(Float)  # 赎回费率
    fee_mgmt = Column(Float)  # 管理费率

    # 索引
    __table_args__ = (
        Index('idx_fund_name', 'name'),
        Index('idx_fund_type', 'type'),
    )


class FundNavHistory(Base):
    """基金净值历史"""
    __tablename__ = 'fund_nav_history'

    id = Column(Integer, primary_key=True, autoincrement=True)
    fund_code = Column(String(12), ForeignKey('fund_info.code'), nullable=False, index=True)
    date = Column(Date, nullable=False)
    nav_unit = Column(Float)
    nav_acc = Column(Float)
    daily_return = Column(Float)  # 日收益率
    estimated_nav = Column(Float)  # 估算净值
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint('fund_code', 'date', name='uq_fund_date'),
        Index('idx_fundnav_date', 'fund_code', 'date'),
    )


# ==================== 投资组合 ====================
class Portfolio(Base):
    """投资组合"""
    __tablename__ = 'portfolios'

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id = Column(String(36), ForeignKey('users.id'), nullable=False, index=True)
    name = Column(String(128), nullable=False)
    description = Column(Text)
    is_default = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    owner = relationship('User', back_populates='portfolios')
    holdings = relationship('PortfolioHolding', back_populates='portfolio',
                           cascade='all, delete-orphan', lazy='dynamic')


class PortfolioHolding(Base):
    """组合持仓"""
    __tablename__ = 'portfolio_holdings'

    id = Column(Integer, primary_key=True, autoincrement=True)
    portfolio_id = Column(String(36), ForeignKey('portfolios.id'), nullable=False, index=True)
    fund_code = Column(String(12), nullable=False)
    shares = Column(Float, default=0)  # 持有份额
    cost_price = Column(Float)  # 成本单价
    cost_amount = Column(Float)  # 成本金额
    buy_date = Column(Date)
    note = Column(Text)
    sort_order = Column(Integer, default=0)

    portfolio = relationship('Portfolio', back_populates='holdings')

    __table_args__ = (Index('idx_holding_portfolio', 'portfolio_id', 'fund_code'),)


# ==================== 实时行情 ====================
class WatchlistItem(Base):
    """自选列表"""
    __tablename__ = 'watchlist'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(36), ForeignKey('users.id'), nullable=False, index=True)
    symbol = Column(String(20), nullable=False)  # 股票代码或基金代码
    symbol_type = Column(String(8), default='stock')  # stock / fund / index
    sort_order = Column(Integer, default=0)
    added_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (UniqueConstraint('user_id', 'symbol', name='uq_user_symbol'),)


class AlertRule(Base):
    """告警规则"""
    __tablename__ = 'alert_rules'

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id = Column(String(36), ForeignKey('users.id'), nullable=False, index=True)
    symbol = Column(String(20), nullable=False)
    condition = Column(String(16))  # above / below / change_above / change_below
    threshold = Column(Float)
    is_active = Column(Boolean, default=True)
    triggered_count = Column(Integer, default=0)
    last_triggered = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)


# ==================== 报告 ====================
class Report(Base):
    """报告记录"""
    __tablename__ = 'reports'

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id = Column(String(36), ForeignKey('users.id'))
    report_type = Column(String(32))  # daily / weekly / portfolio
    title = Column(String(256))
    file_path = Column(String(512))
    status = Column(String(16), default='pending')  # pending / processing / ready / failed
    size_kb = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime)


# ==================== 审计日志 ====================
class AuditLog(Base):
    """操作审计日志"""
    __tablename__ = 'audit_logs'

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(String(36), ForeignKey('users.id'), nullable=True, index=True)
    action = Column(String(64), nullable=False)  # login / create / update / delete / export
    resource_type = Column(String(32))  # user / portfolio / fund / report
    resource_id = Column(String(64))
    detail = Column(JSON)
    ip_address = Column(String(45))
    user_agent = Column(String(512))
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    __table_args__ = (Index('idx_audit_action', 'action', 'created_at'),)


# ==================== 系统配置 ====================
class SystemConfig(Base):
    """系统配置键值对"""
    __tablename__ = 'system_config'

    key = Column(String(128), primary_key=True)
    value = Column(Text)
    description = Column(String(256))
    updated_by = Column(String(36))
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ==================== 商业化计费（REQ-16 / REQ-11） ====================
# 数据全部落库（SQLAlchemy），跨 gunicorn 多 worker 由数据库连接池与唯一约束保证
# 一致性与幂等，替代原先的内存字典 + JSON 文件（多进程下会丢订单/订阅）。
class BillingSubscription(Base):
    """订阅记录：scope_type/scope_id 决定落在 租户 或 用户。

    scope_type = 'tenant' | 'user'
    scope_id   = 租户ID 或 用户ID
    唯一约束 (scope_type, scope_id) 保证每个 scope 仅一条有效订阅。
    """
    __tablename__ = 'billing_subscriptions'

    id = Column(Integer, primary_key=True, autoincrement=True)
    scope_type = Column(String(16), nullable=False)
    scope_id = Column(String(64), nullable=False)
    plan = Column(String(32), default='free')  # free / pro / enterprise
    status = Column(String(16), default='active')  # active / trial / cancelled / expired
    started_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime)
    trial = Column(Boolean, default=False)
    trial_ends_at = Column(DateTime)
    seats = Column(Integer, default=1)
    order_id = Column(String(64))
    operator = Column(String(64))
    note = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint('scope_type', 'scope_id', name='uq_billing_scope'),
        Index('idx_billing_scope_plan', 'scope_type', 'scope_id', 'plan'),
    )


class BillingOrder(Base):
    """支付订单（未支付/已支付/退款等）。order_id 全局唯一。"""
    __tablename__ = 'billing_orders'

    id = Column(Integer, primary_key=True, autoincrement=True)
    order_id = Column(String(64), unique=True, nullable=False, index=True)
    scope_type = Column(String(16), nullable=False)
    scope_id = Column(String(64), nullable=False)
    user_id = Column(String(64))
    plan_code = Column(String(32))
    plan_name = Column(String(128))
    amount_cents = Column(Integer, default=0)
    channel = Column(String(32))  # alipay_web / wechat_native / manual ...
    status = Column(String(16), default='pending')  # pending/paid/refunded/closed/failed
    created_at = Column(DateTime, default=datetime.utcnow)
    paid_at = Column(DateTime)
    trade_no = Column(String(128), index=True)
    extra = Column(JSON)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class BillingNonce(Base):
    """回调幂等：已处理过的第三方交易号。唯一约束保证跨进程不重复入账。"""
    __tablename__ = 'billing_nonces'

    id = Column(Integer, primary_key=True, autoincrement=True)
    trade_no = Column(String(128), unique=True, nullable=False, index=True)
    channel = Column(String(32))
    used_at = Column(DateTime, default=datetime.utcnow)


class BillingQuota(Base):
    """每日配额用量（按 scope + quota_key + 天 唯一）。"""
    __tablename__ = 'billing_quota'

    id = Column(Integer, primary_key=True, autoincrement=True)
    scope_type = Column(String(16), nullable=False)
    scope_id = Column(String(64), nullable=False)
    quota_key = Column(String(32), nullable=False)
    day = Column(String(8), nullable=False)  # YYYYMMDD
    used = Column(Integer, default=0)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint('scope_type', 'scope_id', 'quota_key', 'day',
                         name='uq_billing_quota'),
    )


def uuid4():
    import uuid
    return uuid.uuid4().hex
