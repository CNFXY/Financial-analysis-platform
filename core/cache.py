"""
FUND-OS 缓存层 v5.0
多级缓存策略：内存 → Redis → 数据库
"""

import json
import hashlib
import time
import os
from typing import Any, Optional, Callable

# 内存缓存（进程内）
_memory_cache: dict[str, tuple[Any, float]] = {}
_MEMORY_TTL = 300  # 默认 5 分钟

# Redis 客户端（可选）
_redis_client = None


def init_redis():
    """初始化 Redis 连接"""
    global _redis_client
    redis_url = os.environ.get('REDIS_URL')
    if not redis_url:
        print('[Cache] REDIS_URL 未配置，使用纯内存缓存')
        return False

    try:
        import redis
        _redis_client = redis.from_url(
            redis_url,
            decode_responses=True,
            socket_timeout=5,
            socket_connect_timeout=3,
        )
        _redis_client.ping()
        print(f'[Cache] Redis 已连接: {redis_url}')
        return True
    except ImportError:
        print('[Cache] redis 包未安装，使用纯内存缓存')
        return False
    except Exception as e:
        print(f'[Cache] Redis 连接失败: {e}')
        return False


def make_cache_key(prefix: str, *args, **kwargs) -> str:
    """生成缓存键"""
    key_data = f"{prefix}:{args}:{kwargs}"
    return f"fo:{hashlib.md5(key_data.encode()).hexdigest()[:16]}"


async def get(key: str) -> Optional[Any]:
    """
    获取缓存值
    优先级：Redis → 内存 → None
    """
    # 1. 尝试 Redis
    if _redis_client:
        try:
            val = _redis_client.get(key)
            if val is not None:
                return json.loads(val)
        except Exception as e:
            print(f'[Cache] Redis get 失败: {e}')

    # 2. 回退到内存缓存
    if key in _memory_cache:
        value, expiry = _memory_cache[key]
        if time.time() < expiry:
            return value
        del _memory_cache[key]

    return None


async def set(key: str, value: Any, ttl: int = _MEMORY_TTL):
    """设置缓存值"""
    expiry = time.time() + ttl

    # 写入内存
    _memory_cache[key] = (value, expiry)

    # 写入 Redis
    if _redis_client:
        try:
            _redis_client.setex(
                key,
                ttl,
                json.dumps(value, ensure_ascii=False, default=str)
            )
        except Exception as e:
            print(f'[Cache] Redis set 失败: {e}')


def invalidate(key_pattern: str):
    """失效匹配的缓存键"""
    # 清除内存中匹配的键
    keys_to_remove = [k for k in _memory_cache if k.startswith(key_pattern)]
    for k in keys_to_remove:
        del _memory_cache[k]

    # Redis 中清除（支持通配符）
    if _redis_client:
        try:
            keys = _redis_client.keys(f'{key_pattern}*')
            if keys:
                _redis_client.delete(*keys)
        except Exception as e:
            print(f'[Cache] Redis invalidate 失败: {e}')


def cached(ttl: int = _MEMORY_TTL, prefix: str = ''):
    """
    缓存装饰器
    用法：
        @cached(ttl=60, prefix='fund:detail')
        async def get_fund_detail(code): ...
    """
    def decorator(func: Callable):
        async def wrapper(*args, **kwargs):
            cache_key = make_cache_key(
                prefix or func.__name__,
                *args, **kwargs
            )

            # 尝试获取缓存
            result = await get(cache_key)
            if result is not None:
                return result

            # 执行函数并缓存结果
            result = await func(*args, **kwargs)
            await set(cache_key, result, ttl=ttl)
            return result
        return wrapper
    return decorator


# 统计信息
_stats = {'hits': 0, 'misses': 0}


def get_stats() -> dict:
    total = _stats['hits'] + _stats['misses']
    return {
        'hits': _stats['hits'],
        'misses': _stats['misses'],
        'hit_rate': round(_stats['hits'] / total * 100, 2) if total else 0,
        'memory_keys': len(_memory_cache),
        'redis_connected': bool(_redis_client),
    }
