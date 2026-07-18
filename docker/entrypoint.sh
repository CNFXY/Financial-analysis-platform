#!/bin/sh
# FUND-OS 容器启动脚本
# 同时启动 Nginx + Flask 应用

set -e

echo "========================================="
echo "  FUND-OS v5.0 启动中..."
echo "  $(date '+%Y-%m-%d %H:%M:%S UTC')"
echo "========================================="

# 初始化数据库
echo "[Init] 检查数据库连接..."
python -c "from models.database import init_db; init_db()"

# 启动 Nginx（前端静态文件 + 反向代理）
echo "[Nginx] 启动..."
nginx

# 启动 Flask 应用（生产模式）
echo "[Flask] 启动应用服务..."
exec python -m gunicorn \
    --bind 0.0.0.0:5000 \
    --workers ${WORKERS:-2} \
    --worker-class gevent \
    --timeout 120 \
    --access-logfile /app/logs/access.log \
    --error-logfile /app/logs/error.log \
    --log-level info \
    "visualization.web_server:create_app()"
