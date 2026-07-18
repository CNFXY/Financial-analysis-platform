"""
FUND-OS 数据库连接管理
支持 SQLite（开发） / PostgreSQL（生产）
"""

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool
from sqlalchemy import event

# 数据库配置
DATABASE_URL = os.environ.get(
    'DATABASE_URL',
    'sqlite:///./data/fund_os.db'  # 默认 SQLite
)

# 引擎配置
if DATABASE_URL.startswith('sqlite'):
    engine = create_engine(
        DATABASE_URL,
        connect_args={'check_same_thread': False},
        poolclass=StaticPool,  # SQLite 单线程池
        echo=False,  # 设为 True 可查看 SQL 日志
    )
else:
    engine = create_engine(
        DATABASE_URL,
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True,  # 连接健康检查
        echo=False,
    )

# 会话工厂
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# SQLite 并发安全：多 worker 下开启 WAL + 较长的 busy_timeout，
# 避免「database is locked」与多进程写损坏。PostgreSQL 不需要。
if DATABASE_URL.startswith('sqlite'):
    @event.listens_for(engine, 'connect')
    def _set_sqlite_pragma(dbapi_conn, conn_record):
        try:
            cur = dbapi_conn.cursor()
            cur.execute('PRAGMA busy_timeout = 5000')
            cur.execute('PRAGMA journal_mode = WAL')
            cur.execute('PRAGMA synchronous = NORMAL')
            cur.close()
        except Exception:
            pass


def get_db() -> Session:
    """FastAPI / Flask 依赖注入：获取数据库会话"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """初始化数据库：创建所有表"""
    from models import Base
    Base.metadata.create_all(bind=engine)
    print(f'[DB] 数据库已初始化: {DATABASE_URL}')


def check_connection() -> bool:
    """检查数据库连接是否正常"""
    try:
        with engine.connect() as conn:
            conn.execute('SELECT 1')
        return True
    except Exception as e:
        print(f'[DB] 连接失败: {e}')
        return False


if __name__ == '__main__':
    init_db()
