"""
FUND-OS 中间件层 v5.0
请求追踪 · 限流 · 安全头 · CORS
"""

import time
import uuid
import hashlib
from functools import wraps
from typing import Optional, Callable

# 限流现统一交由 core.rate_limiter（Redis 优先 / 内存兜底）实现
from fund_estimation_system.core.rate_limiter import (
    get_rate_limiter, get_client_ip, rate_limit as _redis_rate_limit,
)


class RequestTracker:
    """请求 ID 追踪中间件"""
    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        # 生成唯一请求 ID
        request_id = environ.get('HTTP_X_REQUEST_ID', uuid.uuid4().hex[:16])
        environ['request_id'] = request_id
        environ['start_time'] = time.time()

        # 自定义 start_response 注入 header
        def custom_start_response(status, headers, exc_info=None):
            duration_ms = (time.time() - environ.get('start_time', time.time())) * 1000
            headers.append(('X-Request-ID', request_id))
            headers.append(('X-Response-Time', f'{duration_ms:.1f}ms'))
            return start_response(status, headers, exc_info)

        return self.app(environ, custom_start_response)


def rate_limit(max_requests: int = 60, window_seconds: int = 60,
               by_ip: bool = True, by_user: bool = False):
    """
    API 限流装饰器（委托 core.rate_limiter：Redis 优先 / 内存兜底）。

    Args:
        max_requests: 时间窗口内最大请求数
        window_seconds: 时间窗口（秒）
        by_ip: 是否按 IP 限制
        by_user: 是否按用户 ID 限制（鉴权后 g.user_id）
    """
    def decorator(f: Callable):
        @wraps(f)
        def wrapper(*args, **kwargs):
            from flask import request, g, jsonify

            limiter = get_rate_limiter()
            parts = ['mw', f.__name__]
            if by_ip:
                parts.append(get_client_ip())
            if by_user:
                uid = getattr(g, 'user_id', None) or request.headers.get('Authorization', 'anonymous')
                parts.append(hashlib.md5(str(uid).encode()).hexdigest()[:12])

            allowed, _remaining, retry = limiter.allow(
                ':'.join(parts), max_requests, window_seconds)
            if not allowed:
                return jsonify({
                    'code': 429003,
                    'message': f'请求过于频繁，请 {retry} 秒后重试',
                    'data': None,
                }), 429
            return f(*args, **kwargs)
        return wrapper
    return decorator


def add_security_headers(response):
    """安全响应头"""
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=()'
    response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'

    # 防止服务器版本泄露
    response.headers['Server'] = 'FUND-OS/5.0'
    return response


def cors_handler(origin: str | None = None, methods: str | None = None):
    """CORS 处理器"""
    def handler(f: Callable):
        @wraps(f)
        def wrapper(*args, **kwargs):
            from flask import request, make_response
            response = make_response(f(*args, **kwargs))

            allowed_origin = origin or '*'
            allowed_methods = methods or 'GET, POST, PUT, DELETE, OPTIONS'
            allowed_headers = 'Authorization, Content-Type, X-Requested-With, X-Request-ID'

            response.headers['Access-Control-Allow-Origin'] = allowed_origin
            response.headers['Access-Control-Allow-Methods'] = allowed_methods
            response.headers['Access-Control-Allow-Headers'] = allowed_headers
            response.headers['Access-Control-Max-Age'] = '86400'

            if request.method == 'OPTIONS':
                response.status_code = 204

            return response
        return wrapper
    return handler


def require_auth(roles: str | list | None = None):
    """认证守卫：要求有效 Token"""
    def decorator(f: Callable):
        @wraps(f)
        def wrapper(*args, **kwargs):
            from flask import request, g, jsonify
            from core.auth import get_current_user_from_token, check_permission

            token_data = get_current_user_from_token(request.headers.get('Authorization'))
            if not token_data:
                return jsonify({
                    'code': 401001,
                    'message': '未授权，请先登录',
                    'data': None,
                }), 401

            g.user_id = token_data.get('sub')
            g.user_role = token_data.get('role')
            g.username = token_data.get('username')

            # 角色检查
            if roles:
                role_list = [roles] if isinstance(roles, str) else roles
                if g.user_role not in role_list and g.user_role != 'admin':
                    return jsonify({
                        'code': 403003,
                        'message': '权限不足',
                        'data': None,
                    }), 403

            return f(*args, **kwargs)
        return wrapper
    return decorator
