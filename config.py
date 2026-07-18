# -*- coding: utf-8 -*-
"""基金估算系统 - 配置管理"""
import os

# Tushare Pro Token（用户需配置）
TUSHARE_TOKEN = os.environ.get("TUSHARE_TOKEN", "")

# Yahoo Finance 配置
YAHOO_REGIONS = {
    "US": {"suffix": ""},
    "HK": {"suffix": ".HK"},
}

# 数据缓存目录
CACHE_DIR = os.path.join(os.path.dirname(__file__), "cache")
os.makedirs(CACHE_DIR, exist_ok=True)

# 演示模式（无Token时使用模拟数据）
DEMO_MODE = not bool(TUSHARE_TOKEN)

# 报告输出目录
REPORT_DIR = os.path.join(os.path.dirname(__file__), "reports")
os.makedirs(REPORT_DIR, exist_ok=True)

# Web服务配置
WEB_HOST = "0.0.0.0"
WEB_PORT = 5000
WEB_DEBUG = True

# ============================================================
# 限流配置（P1：接 Redis）
# REDIS_URL 未配置时自动降级为「进程内内存限流」（仅单 worker 有效）。
# 多 worker / 多机部署务必配置 Redis，否则限流可被拆分请求绕过。
# 阈值（每 IP 每分钟）：
#   RATE_LIMIT_GLOBAL_PER_MIN  全局 API 限流
#   RATE_LIMIT_LOGIN_PER_MIN   登录（防暴破）
#   RATE_LIMIT_REGISTER_PER_MIN 注册（防批量注册）
# ============================================================
REDIS_URL = os.environ.get("REDIS_URL", "")  # 例: redis://localhost:6379/0
RATE_LIMIT_GLOBAL_PER_MIN = int(os.environ.get("RATE_LIMIT_GLOBAL_PER_MIN", 120))
RATE_LIMIT_LOGIN_PER_MIN = int(os.environ.get("RATE_LIMIT_LOGIN_PER_MIN", 10))
RATE_LIMIT_REGISTER_PER_MIN = int(os.environ.get("RATE_LIMIT_REGISTER_PER_MIN", 5))

# ============================================================
# 支付与订阅配置（REQ-16）
# PAYMENT_MODE = sandbox（沙箱/演示） | production（生产）
# 沙箱：沙箱网关 + 模拟回调 + 本地扫码页（无需真实商户号）
# 生产：需要 ALIPAY_APP_ID/ALIPAY_PRIVATE_KEY/ALIPAY_PUBLIC_KEY 与
#       WECHAT_APP_ID/WECHAT_MCH_ID/WECHAT_API_KEY
#
# 证书加载顺序：优先读 *_PATH 指向的 PEM/密钥文件；文件不存在时回退到
# 同名内联 *_KEY 字符串（适合测试/CI）。生产环境强烈建议用 *_PATH 从
# 密钥文件加载，避免明文密钥出现在进程环境变量中。
# ============================================================
PAYMENT_MODE = os.environ.get("PAYMENT_MODE", "sandbox")  # 默认沙箱，确保本地能跑

# 支付宝（沙箱申请：https://open.alipay.com/develop/sandbox/account）
ALIPAY_APP_ID = os.environ.get("ALIPAY_APP_ID", "2021000000000000")
# 应用私钥（PEM，含 -----BEGIN RSA PRIVATE KEY-----）
ALIPAY_PRIVATE_KEY = os.environ.get("ALIPAY_PRIVATE_KEY", "sandbox_private_key_placeholder")
ALIPAY_PRIVATE_KEY_PATH = os.environ.get("ALIPAY_PRIVATE_KEY_PATH", "")
# 支付宝公钥（PEM，平台给的「支付宝公钥」，不是应用公钥）
ALIPAY_PUBLIC_KEY = os.environ.get("ALIPAY_PUBLIC_KEY", "sandbox_public_key_placeholder")
ALIPAY_PUBLIC_KEY_PATH = os.environ.get("ALIPAY_PUBLIC_KEY_PATH", "")

# 微信支付（v2，文档：https://pay.weixin.qq.com/wiki/doc/api/native.php）
WECHAT_APP_ID = os.environ.get("WECHAT_APP_ID", "wx0000000000000000")
WECHAT_MCH_ID = os.environ.get("WECHAT_MCH_ID", "0000000000")
# API v2 密钥（32 字节，商户平台「API 安全」中设置），用于 MD5 签名与回调验签
WECHAT_API_KEY = os.environ.get("WECHAT_API_KEY", "sandbox_wechat_api_key_32bytes_demo")
WECHAT_API_KEY_PATH = os.environ.get("WECHAT_API_KEY_PATH", "")
# 微信支付证书序列号（v3 才需要；本系统使用 v2，可留空）
WECHAT_CERT_SERIAL = os.environ.get("WECHAT_CERT_SERIAL", "")

# 通知与回跳地址（生产请改为 https 公网域名）
PAYMENT_NOTIFY_BASE = os.environ.get("PAYMENT_NOTIFY_BASE", "http://127.0.0.1:5000")
PAYMENT_RETURN_URL = os.environ.get("PAYMENT_RETURN_URL", "http://127.0.0.1:5000/billing/return")

# 二维码输出目录（沙箱模式生成真实可扫描二维码 PNG，供前端 <img> 展示）
# 路径指向 Web 服务的 static 目录，URL 前缀为 /static/pay_qr/<order_id>.png
QR_CODE_DIR = os.path.join(os.path.dirname(__file__), "visualization", "static", "pay_qr")
os.makedirs(QR_CODE_DIR, exist_ok=True)

# ============================================================
# 站点与合规配置（P2：合规清单）
# 以下均为「公开展示信息」，生产务必替换为真实值（尤其 ICP/公安备案号）。
# 通过环境变量覆盖；留空时前端回退到默认占位文案。
# ============================================================
SITE_NAME = os.environ.get("SITE_NAME", "FUND-OS 智能基金估算系统")
COMPANY_NAME = os.environ.get("COMPANY_NAME", "请填写运营主体公司全称")
# ICP 备案号（工信部，例：京ICP备12345678号-1）
# 公安备案号（例：京公网安备11010802000000号）
ICP_BEIAN = os.environ.get("ICP_BEIAN", "")
POLICE_BEIAN = os.environ.get("POLICE_BEIAN", "")
CONTACT_EMAIL = os.environ.get("CONTACT_EMAIL", "support@example.com")
SERVICE_TEL = os.environ.get("SERVICE_TEL", "")
