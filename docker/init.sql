-- FUND-OS 数据库初始化脚本
-- PostgreSQL 首次启动时自动执行

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 创建默认管理员用户（密码: admin123）
INSERT INTO users (id, username, email, password_hash, role, is_active)
VALUES (
    '00000000-0000-0000-0000-000000000001',
    'admin',
    'admin@fund-os.local',
    'salt$hash',  -- 实际由 auth.hash_password() 生成
    'admin',
    true
) ON CONFLICT (id) DO NOTHING;

-- 创建系统配置初始数据
INSERT INTO system_config (key, value, description)
VALUES
    ('app.name', 'FUND-OS v5.0', '应用名称'),
    ('app.version', '5.0.0', '应用版本'),
    ('fund.estimate.models_count', '6', '估算模型数量'),
    ('realtime.update_interval', '3', '行情更新间隔(秒)'),
    ('cache.ttl.default', '300', '默认缓存TTL(秒)'),
    ('rate.limit.requests_per_minute', '60', 'API 每分钟请求限制')
ON CONFLICT (key) DO NOTHING;

NOTICE 'FUND-OS 数据库初始化完成';
