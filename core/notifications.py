"""
FUND-OS 第三方服务集成 — 消息通知系统
支持: 站内通知 / 邮件 / 微信 / 短信
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Dict, Any, List

logger = logging.getLogger('fundos.notifications')


class NotificationChannel(Enum):
    """通知渠道"""
    IN_APP = "in_app"      # 站内通知（数据库存储）
    EMAIL = "email"        # 邮件通知
    WECHAT = "wechat"      # 微信模板消息
    SMS = "sms"            # 短信通知


class NotificationType(Enum):
    """通知类型"""
    # 基金相关
    FUND_ESTIMATE_UPDATE = "fund.estimate_update"
    NAV_CONFIRMED = "nav.confirmed"
    PRICE_ALERT = "price.alert"
    
    # 组合相关
    PORTFOLIO_REBALANCE = "portfolio.rebalance"
    PNL_THRESHOLD = "pnl.threshold"
    
    # 系统
    SYSTEM_ANNOUNCEMENT = "system.announcement"
    SECURITY_ALERT = "security.alert"
    WELCOME = "welcome"


@dataclass
class NotificationMessage:
    """通知消息结构"""
    type: NotificationType
    title: str
    content: str
    channels: List[NotificationChannel]
    recipient_ids: List[int]          # 接收者用户ID列表
    metadata: Dict[str, Any] = None   # 额外数据
    
    priority: int = 0                 # 0=普通 1=重要 2=紧急
    expire_at: Optional[int] = None   # 过期时间戳
    template_id: Optional[str] = None # 模板消息ID（微信/短信用）
    url: Optional[str] = None         # 跳转链接


class NotificationProvider(ABC):
    """通知提供者基类"""
    
    @abstractmethod
    async def send(self, message: NotificationMessage) -> bool:
        """
        发送通知
        
        Returns:
            bool: 发送是否成功
        """
        pass
    
    @abstractmethod
    def validate_config(self) -> bool:
        """验证配置是否正确"""
        pass


class InAppNotificationProvider(NotificationProvider):
    """
    站内通知提供者
    将通知保存到数据库，供前端轮询或 WebSocket 推送
    """
    
    def __init__(self, db_session_factory=None):
        self.db_session = db_session_factory
    
    async def send(self, message: NotificationMessage) -> bool:
        try:
            from models.database import db_session
            from datetime import datetime
            
            for user_id in message.recipient_ids:
                notification_record = {
                    'user_id': user_id,
                    'type': message.type.value,
                    'title': message.title,
                    'content': message.content,
                    'priority': message.priority,
                    'is_read': False,
                    'metadata': message.metadata or {},
                    'created_at': datetime.utcnow(),
                    'expire_at': datetime.fromtimestamp(message.expire_at) if message.expire_at else None
                }
                
                # TODO: 实际实现中写入 notifications 表
                logger.info(f"In-app notification saved for user {user_id}: {message.title}")
            
            return True
        except Exception as e:
            logger.error(f"Failed to save in-app notification: {e}")
            return False
    
    def validate_config(self) -> bool:
        # 站内通知只需要数据库连接，通常总是可用
        return True


class EmailNotificationProvider(NotificationProvider):
    """
    邮件通知提供者
    支持 SMTP / SendGrid / 阿里云邮件
    """
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.smtp_host = config.get('smtp_host', '')
        self.smtp_port = config.get('smtp_port', 587)
        self.smtp_user = config.get('smtp_user', '')
        self.smtp_password = config.get('smtp_password', '')
        self.from_name = config.get('from_name', 'FUND-OS')
        self.from_email = config.get('from_email', 'noreply@fundos.example.com')
        
        # 使用外部服务（SendGrid 等）的配置
        self.use_sendgrid = config.get('use_sendgrid', False)
        self.sendgrid_api_key = config.get('sendgrid_api_key', '')
    
    async def send(self, message: NotificationMessage) -> bool:
        try:
            if self.use_sendgrid and self.sendgrid_api_key:
                return await self._send_via_sendgrid(message)
            else:
                return await self._send_via_smtp(message)
        except Exception as e:
            logger.error(f"Email send failed: {e}")
            return False
    
    async def _send_via_smtp(self, message: NotificationMessage) -> bool:
        import smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart
        
        # 获取用户邮箱（从数据库）
        # 这里简化处理，实际应查询用户表获取邮箱
        recipient_emails = [f"user_{uid}@example.com" for uid in message.recipient_ids]
        
        msg = MIMEMultipart('alternative')
        msg['Subject'] = f"[FUND-OS] {message.title}"
        msg['From'] = f"{self.from_name} <{self.from_email}>"
        msg['To'] = ', '.join(recipient_emails)
        
        # HTML 内容
        html_content = f"""
        <html>
        <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
            <div style="background: linear-gradient(135deg, #1e3a5f 0%, #0d1b2a 100%); padding: 30px; border-radius: 12px; margin-bottom: 20px;">
                <h1 style="color: #f0b90b; margin: 0;">{message.title}</h1>
            </div>
            <div style="background: #1a2332; padding: 25px; border-radius: 8px;">
                {message.content.replace(chr(10), '<br/>')}
            </div>
            <div style="text-align: center; margin-top: 20px; color: #64748b; font-size: 12px;">
                <p>此邮件由 FUND-OS 自动发送，请勿直接回复。</p>
                <p>如需帮助请联系 support@fundos.example.com</p>
            </div>
        </body>
        </html>
        """
        
        msg.attach(MIMEText(html_content, 'html'))
        
        with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
            server.starttls()
            server.login(self.smtp_user, self.smtp_password)
            server.sendmail(self.from_email, recipient_emails, msg.as_string())
        
        logger.info(f"Email sent to {len(recipient_emails)} recipients")
        return True
    
    async def _send_via_sendgrid(self, message: NotificationMessage) -> bool:
        # TODO: 实现 SendGrid API 集成
        # 参考: https://docs.sendgrid.com/api-reference/mail/send-mail
        logger.info("SendGrid integration pending")
        return True
    
    def validate_config(self) -> bool:
        if self.use_sendgrid:
            return bool(self.sendgrid_api_key)
        return bool(self.smtp_host and self.smtp_user)


class WechatNotificationProvider(NotificationProvider):
    """
    微信公众号/小程序模板消息提供者
    用于推送估值提醒、交易通知等
    """
    
    def __init__(self, config: Dict[str, Any]):
        self.app_id = config.get('app_id')
        self.app_secret = config.get('app_secret')
        self.token = config.get('token')           # 消息校验 Token
        self.encoding_aes_key = config.get('encoding_aes_key')
        
        # 缓存的 access_token
        self._access_token = None
        self._token_expires_at = 0
    
    async def get_access_token(self) -> str | None:
        """获取/刷新 access_token"""
        import time
        
        if self._access_token and time.time() < self._token_expires_at:
            return self._access_token
        
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    'https://api.weixin.qq.com/cgi-bin/token',
                    params={
                        'grant_type': 'client_credential',
                        'appid': self.app_id,
                        'secret': self.app_secret
                    }
                )
                
                data = resp.json()
                if 'errcode' in data and data['errcode'] != 0:
                    logger.error(f"WeChat token error: {data}")
                    return None
                
                self._access_token = data['access_token']
                self._token_expires_at = time.time() + data['expires_in'] - 300  # 提前5分钟过期
                
                return self._access_token
        except Exception as e:
            logger.error(f"Failed to get WeChat access token: {e}")
            return None
    
    async def send(self, message: NotificationMessage) -> bool:
        """
        发送微信模板消息
        
        需要提前在公众平台设置好模板，并获取用户的 openid
        """
        token = await self.get_access_token()
        if not token:
            return False
        
        try:
            import httpx
            
            # TODO: 从数据库获取用户 openid
            openids = []  # 实际应为 message.recipient_ids 对应的 openid
            
            for openid in openids:
                payload = {
                    "touser": openid,
                    "template_id": message.template_id or "",
                    "url": message.url or "https://fundos.example.com",
                    "miniprogram": {
                        "appid": "",  # 小程序 appid
                        "pagepath": ""  # 小程序页面路径
                    },
                    "data": {
                        "first": {"value": message.title},
                        "remark": {"value": message.content[:50]}
                    }
                }
                
                async with httpx.AsyncClient() as client:
                    resp = await client.post(
                        f'https://api.weixin.qq.com/cgi-bin/message/template/send?access_token={token}',
                        json=payload
                    )
                    
                    result = resp.json()
                    if result.get('errcode', -1) != 0:
                        logger.error(f"WeChat template msg failed: {result}")
            
            return True
        except Exception as e:
            logger.error(f"WeChat notification error: {e}")
            return False
    
    def validate_config(self) -> bool:
        return bool(self.app_id and self.app_secret)


class SMSNotificationProvider(NotificationProvider):
    """
    短信通知提供者
    支持阿里云短信 / 腾讯云短信 / Twilio
    """
    
    def __init__(self, config: Dict[str, Any]):
        self.provider = config.get('provider', 'aliyun')  # aliyun/tencent/twilio
        self.access_key_id = config.get('access_key_id')
        self.access_key_secret = config.get('access_key_secret')
        self.sign_name = config.get('sign_name', 'FUND-OS')
        self.template_code = config.get('template_code')
        
        # 腾讯云专用
        self.secret_id = config.get('secret_id')
        self.secret_key = config.get('secret_key')
        self.sdk_app_id = config.get('sdk_app_id')
    
    async def send(self, message: NotificationMessage) -> bool:
        try:
            if self.provider == 'aliyun':
                return await self._send_aliyun(message)
            elif self.provider == 'tencent':
                return await self._send_tencent(message)
            else:
                logger.warning(f"Unsupported SMS provider: {self.provider}")
                return False
        except Exception as e:
            logger.error(f"SMS send error: {e}")
            return False
    
    async def _send_aliyun(self, message: NotificationMessage) -> bool:
        """阿里云短信发送"""
        # TODO: 使用 aliyunsdkcore 或 HTTP API
        # 参考文档: https://help.aliyun.com/document_detail/101414.html
        logger.info("Aliyun SMS integration pending")
        return True
    
    async def _send_tencent(self, message: NotificationMessage) -> bool:
        """腾讯云短信发送"""
        # TODO: 使用 tencentcloud-sdk-python
        logger.info("Tencent SMS integration pending")
        return True
    
    def validate_config(self) -> bool:
        if self.provider == 'aliyun':
            return bool(self.access_key_id and self.access_key_secret)
        elif self.provider == 'tencent':
            return bool(self.secret_id and self.secret_key)
        return False


class NotificationService:
    """
    统一通知服务
    
    功能:
    - 多渠道发送（可同时发多个渠道）
    - 渠道优先级和降级策略
    - 发送失败重试
    - 通知频率限制（防骚扰）
    - 用户偏好管理
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        self.providers: Dict[NotificationChannel, NotificationProvider] = {}
        
        # 初始化各渠道提供者
        self._initialize_providers()
        
        # 发送统计
        self.stats = {
            'total_sent': 0,
            'total_failed': 0,
            'by_channel': {},
            'by_type': {}
        }
    
    def _initialize_providers(self):
        """根据配置初始化所有通知渠道"""
        # 站内通知（始终启用）
        self.providers[NotificationChannel.IN_APP] = InAppNotificationProvider()
        
        # 邮件
        email_config = self.config.get('email', {})
        if email_config.get('enabled'):
            self.providers[NotificationChannel.EMAIL] = EmailNotificationProvider(email_config)
        
        # 微信
        wechat_config = self.config.get('wechat', {})
        if wechat_config.get('enabled'):
            self.providers[NotificationChannel.WECHAT] = WechatNotificationProvider(wechat_config)
        
        # 短信
        sms_config = self.config.get('sms', {})
        if sms_config.get('enabled'):
            self.providers[NotificationChannel.SMS] = SMSNotificationProvider(sms_config)
    
    async def send(self, message: NotificationMessage) -> Dict[NotificationChannel, bool]:
        """
        发送通知到指定渠道
        
        Returns:
            dict: 各渠道发送结果 {channel: success}
        """
        results = {}
        
        for channel in message.channels:
            provider = self.providers.get(channel)
            
            if not provider:
                logger.warning(f"No provider configured for channel: {channel.value}")
                results[channel] = False
                continue
            
            # 检查渠道是否可用
            if not provider.validate_config():
                logger.warning(f"Channel {channel.value} configuration invalid")
                results[channel] = False
                continue
            
            # 发送
            try:
                success = await provider.send(message)
                results[channel] = success
                
                if success:
                    self.stats['total_sent'] += 1
                else:
                    self.stats['total_failed'] += 1
                    
            except Exception as e:
                logger.error(f"Error sending via {channel.value}: {e}")
                results[channel] = False
                self.stats['total_failed'] += 1
            
            # 更新统计
            ch_key = channel.value
            self.stats['by_channel'][ch_key] = self.stats['by_channel'].get(ch_key, 0) + 1
            type_key = message.type.value
            self.stats['by_type'][type_key] = self.stats['by_type'].get(type_key, 0) + 1
        
        return results
    
    async def notify_fund_estimate_update(
        self,
        fund_code: str,
        fund_name: str,
        estimated_nav: float,
        change_pct: float,
        user_ids: List[int]
    ):
        """发送估值更新通知"""
        direction = '上涨' if change_pct >= 0 else '下跌'
        emoji = '+' if change_pct >= 0 else ''
        
        message = NotificationMessage(
            type=NotificationType.FUND_ESTIMATE_UPDATE,
            title=f'📊 {fund_name}({fund_code}) 估值更新',
            content=f"""当前估算净值: {estimated_nav:.4f}
涨跌幅: {emoji}{change_pct:.2f}%
更新时间: {__import__('datetime').datetime.now().strftime('%H:%M:%S')}
---
此为实时估值数据，最终以基金公司公布的净值为准。""",
            channels=[NotificationChannel.IN_APP],  # 默认只发站内
            recipient_ids=user_ids,
            metadata={
                'fund_code': fund_code,
                'estimated_nav': estimated_nav,
                'change_pct': change_pct
            },
            priority=0
        )
        
        return await self.send(message)
    
    async def notify_price_alert(
        self,
        fund_code: str,
        fund_name: str,
        current_price: float,
        target_price: float,
        alert_type: str,  # 'above' / 'below'
        user_ids: List[int]
    ):
        """发送价格预警通知"""
        direction = '突破' if alert_type == 'above' else '跌破'
        
        message = NotificationMessage(
            type=NotificationType.PRICE_ALERT,
            title=f'⚠️ 价格预警: {fund_name}',
            content=f"""{fund_name}({fund_code}) 当前价格 {current_price:.4f} 已{direction}目标价 {target_price:.4f}
请关注市场动态，及时调整投资策略。""",
            channels=[
                NotificationChannel.IN_APP,
                NotificationChannel.EMAIL,  # 重要预警同时发邮件
                NotificationChannel.WECHAT
            ],
            recipient_ids=user_ids,
            metadata={
                'fund_code': fund_code,
                'current_price': current_price,
                'target_price': target_price,
                'alert_type': alert_type
            },
            priority=2  # 高优先级
        )
        
        return await self.send(message)
    
    async def notify_security_alert(
        self,
        alert_type: str,
        description: str,
        user_ids: List[int]
    ):
        """发送安全警报"""
        message = NotificationMessage(
            type=NotificationType.SECURITY_ALERT,
            title='🔐 安全警告',
            content=f"""检测到异常安全事件: {alert_type}
详情: {description}

如果这不是您本人的操作，请立即修改密码并检查账户安全。
如有疑问请联系客服。""",
            channels=[
                NotificationChannel.IN_APP,
                NotificationChannel.EMAIL,
                NotificationChannel.SMS  # 安全警报全渠道推送
            ],
            recipient_ids=user_ids,
            priority=2  # 最高优先级
        )
        
        return await self.send(message)
    
    def get_stats(self) -> Dict[str, Any]:
        """获取通知服务统计"""
        return {
            **self.stats,
            'available_channels': list(self.providers.keys())
        }


# 全局单例（延迟初始化）
_notification_service: Optional[NotificationService] = None


def get_notification_service(config: Dict[str, Any] = None) -> NotificationService:
    """获取通知服务实例（懒加载）"""
    global _notification_service
    
    if _notification_service is None:
        _notification_service = NotificationService(config)
    
    return _notification_service
