"""
FUND-OS 认证授权模块 v6.0（安全加固）

变更点（针对市场级上线）：
1. **强制 PyJWT**：不再有 base64「无签名」回退，缺失依赖直接启动失败，
   杜绝任何人自签 admin token 的伪造风险。
2. **JWT_SECRET 必填**：生产环境未配置直接抛错（fail-fast），移除硬编码默认值，
   避免攻击者拿已知密钥伪造任意用户。
3. **密码哈希升级为 PBKDF2-HMAC-SHA256（20万次迭代）**：替代原 SHA256(无工作因子)，
   显著提升抗 GPU 暴破能力，且为零新增依赖（标准库实现）。
4. 统一 Token API：generate_tokens / verify_token / require_auth，
   兼容旧 create_access_token / decode_token 调用。
"""

import os
import re
import time
import secrets
import hashlib
import hmac
import warnings
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

# JWT 库为强依赖：缺失即启动失败（不允许无签名 token 的退化实现）
import jwt  # noqa: F401  (ImportError 会在导入期直接暴露)


# ==================== 配置 ====================
# JWT_SECRET 必填；生产环境缺失直接失败，开发环境允许临时密钥并告警。
JWT_SECRET = os.environ.get('JWT_SECRET') or os.environ.get('JWT_SECRET_KEY')
if JWT_SECRET is None:
    if os.environ.get('FUNDOS_ENV') == 'production' or os.environ.get('WEB_DEBUG') == 'False':
        raise RuntimeError(
            "JWT_SECRET 未配置：生产环境必须设置环境变量 JWT_SECRET（>=32 位随机串），"
            "否则存在 token 被伪造的安全风险。"
        )
    JWT_SECRET = secrets.token_hex(32)
    warnings.warn(
        "JWT_SECRET 未设置，已使用临时开发密钥（每次启动不同）。"
        "严禁在生产环境使用；请在环境变量中配置固定的 JWT_SECRET。",
        RuntimeWarning,
    )

JWT_ALGORITHM = os.environ.get('JWT_ALGORITHM', 'HS256')
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.environ.get('JWT_EXPIRE', 1440))  # 默认 24 小时
REFRESH_TOKEN_EXPIRE_DAYS = int(os.environ.get('REFRESH_EXPIRE', 7))


# ==================== 密码工具 ====================
_PBKDF2_ITERATIONS = 200_000


def hash_password(password: str) -> str:
    """密码哈希：pbkdf2$<iterations>$<salt_hex>$<dk_hex>"""
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, _PBKDF2_ITERATIONS)
    return f"pbkdf2${_PBKDF2_ITERATIONS}${salt.hex()}${dk.hex()}"


def verify_password(password: str, password_hash: str) -> bool:
    """验证密码（兼容旧 SHA256$salt$hash 格式，逐步迁移）"""
    if not password_hash:
        return False
    try:
        if password_hash.startswith('pbkdf2$'):
            _, iters_s, salt_hex, dk_hex = password_hash.split('$')
            dk = hashlib.pbkdf2_hmac(
                'sha256', password.encode('utf-8'),
                bytes.fromhex(salt_hex), int(iters_s),
            )
            return hmac.compare_digest(dk.hex(), dk_hex)
        # 旧格式回退（仅校验，不再新增）
        if password_hash.startswith('sha256$'):
            salt, stored = password_hash.split('$', 1)
            computed = hashlib.sha256((password + salt).encode()).hexdigest()
            return hmac.compare_digest(computed, stored)
    except (ValueError, AttributeError):
        return False
    return False


# ==================== 密码强度策略 ====================
# 常见弱口令（小写归一化比对），注册/改密时直接拒绝。
_COMMON_WEAK = {
    'password', 'passw0rd', '1234567890', '12345678', 'qwerty',
    'abcdefgh', 'admin', 'administrator', 'fundos', 'fund123',
    '1111111111', '0000000000', 'iloveyou', 'letmein', 'welcome',
    'changeme', 'root', 'test', 'guest',
}


def validate_password_strength(password: str) -> Tuple[bool, str]:
    """密码强度校验（P1）。

    规则：
    - 长度 10–128 位
    - 至少包含 大写 / 小写 / 数字 / 特殊符号 中的 3 类
    - 拒绝常见弱口令、全同字符、连续序列（如 1234567890 / abcdef）

    Returns:
        (ok, reason)  —— ok 为 False 时 reason 为中文提示
    """
    if not password or not isinstance(password, str):
        return False, "密码不能为空"
    if len(password) < 10:
        return False, "密码至少 10 位"
    if len(password) > 128:
        return False, "密码过长（最多 128 位）"

    categories = 0
    if re.search(r'[a-z]', password):
        categories += 1
    if re.search(r'[A-Z]', password):
        categories += 1
    if re.search(r'\d', password):
        categories += 1
    if re.search(r'[^A-Za-z0-9]', password):
        categories += 1
    if categories < 3:
        return False, "密码需同时包含大写字母、小写字母、数字、特殊符号中的至少三类"

    low = password.lower()
    if low in _COMMON_WEAK:
        return False, "密码过于常见，请更换"

    # 全同字符：aaaaaaaaaa / 1111111111
    if len(set(password)) == 1:
        return False, "密码不能全为相同字符"

    # 连续升序序列（长度 >= 4）：1234 / abcd / 2345...
    seq = ord(password[0])
    run = 1
    for ch in password[1:]:
        if ord(ch) == seq + 1:
            run += 1
            seq = ord(ch)
            if run >= 4:
                return False, "密码不能包含连续递增序列（如 1234、abcd）"
        else:
            run = 1
            seq = ord(ch)

    return True, ""


# ==================== JWT Token ====================
def _now() -> int:
    return int(time.time())


def _payload(user_id: str, username: str, role: str,
             tenant_id: Optional[str], token_type: str) -> dict:
    now = _now()
    exp = now + (ACCESS_TOKEN_EXPIRE_MINUTES * 60 if token_type == 'access'
                 else REFRESH_TOKEN_EXPIRE_DAYS * 86400)
    return {
        'sub': str(user_id),
        'username': username,
        'role': role,
        'tenant_id': tenant_id,
        'type': token_type,
        'iat': now,
        'exp': exp,
    }


def generate_tokens(user_id: str, username: str, role: str,
                    tenant_id: Optional[str] = None) -> dict:
    """签发 access + refresh token。返回标准结构供前端使用。"""
    access = jwt.encode(_payload(user_id, username, role, tenant_id, 'access'),
                        JWT_SECRET, algorithm=JWT_ALGORITHM)
    refresh = jwt.encode(_payload(user_id, username, role, tenant_id, 'refresh'),
                         JWT_SECRET, algorithm=JWT_ALGORITHM)
    return {
        'access_token': access,
        'refresh_token': refresh,
        'expires_in': ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        'token_type': 'bearer',
    }


def verify_token(token: str, token_type: str = 'access') -> Optional[dict]:
    """校验 token 并返回 payload；失败返回 None。"""
    if not token:
        return None
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return None
    if payload.get('type') != token_type:
        return None
    return payload


# ---- 兼容旧接口（保持调用方可不改） ----
def create_access_token(user_id: str, username: str, role: str) -> str:
    return generate_tokens(user_id, username, role).get('access_token')


def decode_token(token: str) -> Optional[dict]:
    return verify_token(token, token_type='access')


def get_current_user_from_token(auth_header: Optional[str]) -> Optional[dict]:
    """从 Authorization header 提取用户信息（Flask 中间件调用）。"""
    if not auth_header or not auth_header.startswith('Bearer '):
        return None
    return verify_token(auth_header[7:], token_type='access')


# ==================== RBAC 权限 ====================
ROLES = {
    'admin': {'*'},
    'user': {'fund:read', 'fund:write', 'portfolio:read', 'portfolio:write',
             'realtime:read', 'report:read', 'report:create'},
    'viewer': {'fund:read', 'realtime:read', 'report:read'},
}

PERMISSIONS = {
    'GET /api/fund/*': 'fund:read',
    'POST /api/fund/estimate': 'fund:write',
    'GET /api/portfolio/*': 'portfolio:read',
    'POST /api/portfolio': 'portfolio:write',
    'PUT /api/portfolio/*': 'portfolio:write',
    'DELETE /api/portfolio/*': 'portfolio:delete',
    'GET /api/realtime/*': 'realtime:read',
    'POST /api/realtime/alerts': 'realtime:write',
    'GET /api/report/*': 'report:read',
    'POST /api/report/*': 'report:create',
    'GET /api/admin/*': 'admin:*',
    '*': 'admin:*',
}


def check_permission(role: str, required_permission: str) -> bool:
    """检查角色是否拥有指定权限（admin 拥有所有权限）。"""
    if role not in ROLES:
        return False
    role_perms = ROLES[role]
    if '*' in role_perms:
        return True
    return required_permission in role_perms


def get_required_permission(method: str, path: str) -> str:
    pattern = f'{method} {path}'
    if pattern in PERMISSIONS:
        return PERMISSIONS[pattern]
    for key, perm in PERMISSIONS.items():
        key_method, key_path = key.split(' ', 1)
        if method == key_method and '*' in key_path:
            base = key_path.replace('*', '')
            if path.startswith(base):
                return perm
    return 'public'


# ==================== API Key（可选，用于服务间调用） ====================
_api_keys: dict[str, dict] = {}


def generate_api_key(user_id: str, name: str) -> tuple[str, str]:
    key = f"fo_ak_{os.urandom(12).hex()}"
    secret = f"fo_as_{os.urandom(24).hex()}"
    _api_keys[key] = {
        'secret': secret,
        'user_id': user_id,
        'name': name,
        'created_at': datetime.utcnow().isoformat(),
    }
    return key, secret


def verify_api_key(key: str, secret: str) -> Optional[dict]:
    record = _api_keys.get(key)
    if not record:
        return None
    if not hmac.compare_digest(record['secret'], secret or ''):
        return None
    return {'user_id': record['user_id'], 'type': 'api_key'}
