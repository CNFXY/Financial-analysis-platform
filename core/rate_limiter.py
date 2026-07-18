# -*- coding: utf-8 -*-
"""分布式限流（Redis 优先，进程内兜底）。

设计目标（对应 P1 限流接 Redis）：
- 多 worker / 多进程部署下，限流计数必须放在共享存储（Redis），
  否则 gunicorn -w 4 时每个 worker 各自计数，攻击者拆分请求即可绕过。
- 未配置 Redis（开发 / CI / 单机）时自动降级为「线程安全的内存计数」，
  保证功能不受影响（只是无法跨进程）。
- 使用固定窗口计数器：INCR + 仅首次 EXPIRE，避免滑动窗口 TTL 被反复重置的坑。
- 提供 Flask 装饰器 rate_limit，便于在蓝图路由上直接使用。
"""
import os
import time
import threading
from functools import wraps
from typing import Optional, Tuple

# redis 为可选依赖：未安装时不强制，自动走内存兜底。
try:
    import redis as _redis_lib  # type: ignore
    _REDIS_AVAILABLE = True
except Exception:  # pragma: no cover
    _redis_lib = None
    _REDIS_AVAILABLE = False


class RateLimiter:
    """限流核心。优先用 Redis，失败/未配置则内存兜底。"""

    def __init__(self, redis_url: Optional[str] = None):
        self.redis_url = redis_url or os.environ.get('REDIS_URL')
        self._redis = None
        self._lock = threading.Lock()
        self._mem: dict[str, list[float]] = {}

        if self.redis_url and _REDIS_AVAILABLE:
            try:
                self._redis = _redis_lib.from_url(
                    self.redis_url,
                    socket_timeout=1,
                    socket_connect_timeout=1,
                    decode_responses=True,
                )
                self._redis.ping()
            except Exception:  # pragma: no cover - 连接失败则降级
                self._redis = None

    # ---- 状态查询（便于运维/测试） ----
    def using_redis(self) -> bool:
        return self._redis is not None

    # ---- 主接口 ----
    def allow(self, key: str, max_requests: int,
              window_seconds: int) -> Tuple[bool, int, int]:
        """判断 key 在窗口内是否仍可放行。

        Returns:
            (allowed, remaining, retry_after_seconds)
        """
        if self._redis is not None:
            return self._allow_redis(key, max_requests, window_seconds)
        return self._allow_mem(key, max_requests, window_seconds)

    def _allow_mem(self, key: str, max_requests: int, window_seconds: int):
        now = time.time()
        with self._lock:
            lst = self._mem.get(key)
            if lst is None:
                lst = []
            cutoff = now - window_seconds
            lst = [t for t in lst if t > cutoff]
            if len(lst) >= max_requests:
                # 距离最早一条离开窗口还需多久
                retry = int(window_seconds - (now - lst[0])) + 1
                self._mem[key] = lst
                return False, 0, max(1, retry)
            lst.append(now)
            self._mem[key] = lst
            return True, max(0, max_requests - len(lst)), 0

    def _allow_redis(self, key: str, max_requests: int, window_seconds: int):
        full = f"fundos:ratelimit:{key}"
        try:
            r = self._redis
            count = r.incr(full)
            if count == 1:
                # 仅首条设置 TTL，得到正确的固定窗口
                r.expire(full, window_seconds)
            if count > max_requests:
                ttl = r.ttl(full)
                return False, 0, max(1, ttl if ttl and ttl > 0 else window_seconds)
            return True, max(0, max_requests - count), 0
        except Exception:
            # Redis 抖动时不阻断业务（fail-open）；仅日志侧应告警
            return True, max_requests, 0


# ==================== 模块级单例 ====================
_default_limiter: Optional[RateLimiter] = None


def get_rate_limiter() -> RateLimiter:
    global _default_limiter
    if _default_limiter is None:
        _default_limiter = RateLimiter()
    return _default_limiter


def get_client_ip() -> str:
    """取得真实客户端 IP（兼容反向代理）。"""
    from flask import request
    xff = request.headers.get('X-Forwarded-For')
    if xff:
        return xff.split(',')[0].strip()
    xri = request.headers.get('X-Real-IP')
    if xri:
        return xri.strip()
    return request.remote_addr or 'unknown'


def rate_limit(max_requests: int = 60, window_seconds: int = 60,
               key_prefix: str = 'route',
               key_func=None):
    """Flask 路由限流装饰器。

    Args:
        max_requests: 窗口内最大请求数
        window_seconds: 时间窗口（秒）
        key_prefix: 计数键前缀，便于区分维度
        key_func: 可选，接收 request 返回额外维度字符串
                  （如按登录名限流：lambda r: r.get_json(silent=True).get('username','')）
    """
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            from flask import request, jsonify
            parts = [key_prefix, request.endpoint or f.__name__, get_client_ip()]
            if key_func is not None:
                try:
                    extra = key_func(request)
                    if extra:
                        parts.append(str(extra))
                except Exception:
                    pass
            allowed, remaining, retry = get_rate_limiter().allow(
                ':'.join(parts), max_requests, window_seconds)
            if not allowed:
                resp = jsonify({
                    'code': 429003,
                    'message': f'请求过于频繁，请 {retry} 秒后重试',
                    'data': None,
                })
                resp.status_code = 429
                resp.headers['Retry-After'] = str(retry)
                return resp
            return f(*args, **kwargs)
        return wrapper
    return decorator


def register_rate_limit_middleware(app, global_per_min: Optional[int] = None,
                                   window_seconds: int = 60) -> bool:
    """为 Flask app 注册全局 API 限流 before_request（与 web_server 同款逻辑）。

    抽离此函数便于在测试中直接复用同一份代码路径：
    - 按客户端 IP 对 /api/* 限流（跳过 OPTIONS / static / 健康检查）
    - Redis 优先，未配置则进程内兜底
    - 限流触发返回 429 + Retry-After
    """
    from flask import request, jsonify
    try:
        import fund_estimation_system.config as _cfg
    except Exception:  # pragma: no cover
        _cfg = None

    limit = global_per_min
    if limit is None:
        limit = getattr(_cfg, 'RATE_LIMIT_GLOBAL_PER_MIN', 120) if _cfg else 120

    @app.before_request
    def _global_rate_limit():
        if request.method == 'OPTIONS':
            return None
        path = request.path
        if path.startswith('/static') or path in ('/healthz', '/readyz'):
            return None
        if not path.startswith('/api'):
            return None
        allowed, _rem, retry = get_rate_limiter().allow(
            f"global:ip:{get_client_ip()}", limit, window_seconds)
        if not allowed:
            resp = jsonify({
                'code': 429003,
                'message': f'请求过于频繁，请 {retry} 秒后重试',
                'data': None,
            })
            resp.status_code = 429
            resp.headers['Retry-After'] = str(retry)
            return resp

    return True
