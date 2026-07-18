# ============================================
# FUND-OS v5.0 多阶段 Docker 构建
# 前端 Vue3 + 后端 Python Flask
# ============================================

# ====== 阶段1: 构建前端 ======
FROM node:20-alpine AS frontend-builder
WORKDIR /build/frontend

COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci --registry=https://registry.npmmirror.com

COPY frontend/ ./
# 先生成 unplugin 全局声明 (src/auto-imports.d.ts, src/components.d.ts)。
# 干净镜像中这些文件不存在, 若直接 'vue-tsc -b' 会因缺全局类型而构建失败。
RUN npm run gen:dts
RUN npm run build

# ====== 阶段2: 运行时镜像 ======
FROM python:3.11-slim AS runtime

LABEL maintainer="FUND-OS Team"
LABEL version="5.0.0"
LABEL description="FUND-OS Intelligent Fund Estimation System"

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ libpq-dev curl nginx \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd -r appuser && useradd -r -g appuser -d /app -s /sbin/nologin appuser

WORKDIR /app

# Python 依赖（分层缓存）
COPY requirements.txt .
RUN pip install --no-cache-dir -i https://mirrors.aliyun.com/pypi/simple -r requirements.txt

# 复制后端代码
COPY . .

# 复制构建好的前端静态文件
COPY --from=frontend-builder /build/frontend/dist ./visualization/dist

# Nginx 配置（前端静态文件 + API 反向代理）
COPY docker/nginx.conf /etc/nginx/nginx.conf

# 数据目录
RUN mkdir -p /app/data /app/logs /app/cache \
    && chown -R appuser:appuser /app

# 暴露端口
EXPOSE 5000 80 443

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:5000/api/health || exit 1

# 启动脚本：同时启动 Nginx + Flask
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

USER appuser
ENTRYPOINT ["/entrypoint.sh"]
