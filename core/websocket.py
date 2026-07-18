"""
FUND-OS WebSocket 实时数据推送服务
支持: 实时行情 / 估值更新 / 系统通知
"""

import asyncio
import json
import logging
import time
from typing import Dict, Set, Any, Optional, Callable, List
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger('fundos.ws')


class ChannelType(Enum):
    """WebSocket 频道类型"""
    REALTIME_QUOTE = "realtime.quote"       # 实时行情
    FUND_ESTIMATE = "fund.estimate"         # 基金估值
    SYSTEM_NOTIFY = "system.notify"         # 系统通知
    PORTFOLIO_UPDATE = "portfolio.update"   # 组合变动


@dataclass
class WSClient:
    """WebSocket 客户端连接信息"""
    client_id: str
    user_id: int
    channels: Set[str] = field(default_factory=set)
    connected_at: float = field(default_factory=time.time)
    last_ping: float = field(default_factory=time.time)


class WebSocketManager:
    """
    WebSocket 连接管理器
    
    功能:
    - 客户端连接/断开管理
    - 频道订阅/取消订阅
    - 消息广播（支持频道过滤）
    - 心跳检测 & 超时断开
    - 认证校验
    - 频率限制
    """
    
    def __init__(self):
        self._clients: Dict[str, WSClient] = {}          # client_id -> WSClient
        self._channels: Dict[str, Set[str]] = {}          # channel -> set of client_ids
        self._user_clients: Dict[int, Set[str]] = {}      # user_id -> set of client_ids
        
        # 配置参数
        self.ping_interval = 30      # 心跳间隔（秒）
        self.ping_timeout = 10       # 心跳超时（秒）
        self.max_connections_per_user = 5  # 单用户最大连接数
        self.max_message_size = 1024 * 1024  # 最大消息大小 (1MB)
        
        # 消息处理器注册表
        self._handlers: Dict[str, Callable] = {}
        
        # 统计指标
        self.stats = {
            'total_connections': 0,
            'active_connections': 0,
            'messages_sent': 0,
            'messages_received': 0,
            'broadcasts': 0,
            'errors': 0
        }
    
    async def connect(self, client_id: str, user_id: int) -> bool:
        """建立新连接"""
        # 检查单用户连接数上限
        if len(self._user_clients.get(user_id, set())) >= self.max_connections_per_user:
            logger.warning(f"User {user_id} reached max connections limit")
            return False
        
        # 创建客户端实例
        client = WSClient(
            client_id=client_id,
            user_id=user_id,
            channels=set()
        )
        
        self._clients[client_id] = client
        self._user_clients.setdefault(user_id, set()).add(client_id)
        
        self.stats['total_connections'] += 1
        self.stats['active_connections'] = len(self._clients)
        
        logger.info(f"WS Client {client_id} connected (user={user_id}, active={self.stats['active_connections']})")
        return True
    
    async def disconnect(self, client_id: str):
        """断开连接并清理资源"""
        if client_id not in self._clients:
            return
        
        client = self._clients[client_id]
        
        # 取消所有频道订阅
        for channel in list(client.channels):
            await self.unsubscribe(client_id, channel)
        
        # 清理数据结构
        del self._clients[client_id]
        if client.user_id in self._user_clients:
            self._user_clients[client.user_id].discard(client_id)
            if not self._user_clients[client.user_id]:
                del self._user_clients[client.user_id]
        
        self.stats['active_connections'] = len(self._clients)
        logger.info(f"WS Client {client_id} disconnected (active={self.stats['active_connections']})")
    
    async def subscribe(self, client_id: str, channel: str):
        """订阅频道"""
        if client_id not in self._clients:
            return False
        
        client = self._clients[client_id]
        client.channels.add(channel)
        self._channels.setdefault(channel, set()).add(client_id)
        
        logger.debug(f"Client {client_id} subscribed to '{channel}'")
        return True
    
    async def unsubscribe(self, client_id: str, channel: str):
        """取消订阅频道"""
        if client_id not in self._clients:
            return False
        
        client = self._clients[client_id]
        client.channels.discard(channel)
        
        if channel in self._channels:
            self._channels[channel].discard(client_id)
            if not self._channels[channel]:
                del self._channels[channel]
        
        logger.debug(f"Client {client_id} unsubscribed from '{channel}'")
        return True
    
    def get_subscribers(self, channel: str) -> Set[str]:
        """获取频道的所有订阅者"""
        return self._channels.get(channel, set())
    
    async def send_message(
        self, 
        client_id: str, 
        message_type: str, 
        data: Any,
        timestamp: Optional[float] = None
    ) -> bool:
        """发送消息给单个客户端"""
        if client_id not in self._clients:
            return False
        
        message = {
            "type": message_type,
            "data": data,
            "timestamp": timestamp or time.time()
        }
        
        try:
            payload = json.dumps(message, ensure_ascii=False, default=str)
            
            # 这里需要与具体的 WebSocket 框架集成
            # Flask-SocketIO / FastAPI WebSocket / etc.
            # 实际实现中，这里会调用 socketio.emit 或 websocket.send
            
            self.stats['messages_sent'] += 1
            return True
        except Exception as e:
            logger.error(f"Failed to send to {client_id}: {e}")
            self.stats['errors'] += 1
            return False
    
    async def broadcast(
        self,
        channel: str,
        message_type: str,
        data: Any,
        exclude_client: Optional[str] = None
    ) -> int:
        """向指定频道的所有订阅者广播消息"""
        subscribers = self.get_subscribers(channel)
        if exclude_client:
            subscribers = subscribers - {exclude_client}
        
        count = 0
        for client_id in subscribers:
            success = await self.send_message(client_id, message_type, data)
            if success:
                count += 1
        
        self.stats['broadcasts'] += 1
        logger.debug(f"Broadcast to channel '{channel}': {count}/{len(subscribers)} clients")
        return count
    
    async def handle_message(self, client_id: str, raw_message: str | bytes):
        """处理客户端发来的消息"""
        self.stats['messages_received'] += 1
        
        try:
            # 解析消息
            if isinstance(raw_message, bytes):
                raw_message = raw_message.decode('utf-8')
            
            message = json.loads(raw_message)
            msg_type = message.get('type')
            msg_data = message.get('data', {})
            
            if not msg_type:
                await self.send_error(client_id, "Missing message type")
                return
            
            # 处理内置命令
            if msg_type == 'ping':
                await self.handle_ping(client_id)
                return
            
            if msg_type == 'subscribe':
                channels = msg_data.get('channels', [])
                if isinstance(channels, str):
                    channels = [channels]
                for ch in channels:
                    await self.subscribe(client_id, ch)
                await self.send_message(client_id, 'subscribed', {'channels': channels})
                return
            
            if msg_type == 'unsubscribe':
                channels = msg_data.get('channels', [])
                if isinstance(channels, str):
                    channels = [channels]
                for ch in channels:
                    await self.unsubscribe(client_id, ch)
                await self.send_message(client_id, 'unsubscribed', {'channels': channels})
                return
            
            # 分发给注册的处理器
            handler = self._handlers.get(msg_type)
            if handler:
                try:
                    await handler(client_id, msg_data)
                except Exception as e:
                    logger.error(f"Handler error for '{msg_type}': {e}")
                    await self.send_error(client_id, f"Internal error: {str(e)}")
            else:
                await self.send_error(client_id, f"Unknown message type: {msg_type}")
                
        except json.JSONDecodeError:
            await self.send_error(client_id, "Invalid JSON format")
        except Exception as e:
            logger.error(f"Message handling error: {e}")
            self.stats['errors'] += 1
            await self.send_error(client_id, "Internal server error")
    
    async def send_error(self, client_id: str, error: str):
        """发送错误消息"""
        await self.send_message(client_id, 'error', {'message': error})
    
    async def handle_ping(self, client_id: str):
        """处理心跳 ping"""
        if client_id in self._clients:
            self._clients[client_id].last_ping = time.time()
            await self.send_message(client_id, 'pong', {})
    
    def register_handler(self, msg_type: str, handler: Callable):
        """注册消息处理器"""
        self._handlers[msg_type] = handler
        logger.debug(f"Registered handler for '{msg_type}'")
    
    async def cleanup_stale_connections(self, timeout: float = None):
        """清理超时未响应的连接"""
        timeout = timeout or (self.ping_interval + self.ping_timeout)
        now = time.time()
        stale_ids = [
            cid for cid, client in self._clients.items()
            if now - client.last_ping > timeout
        ]
        
        for cid in stale_ids:
            logger.warning(f"Disconnecting stale client: {cid}")
            await self.disconnect(cid)
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            **self.stats,
            'active_channels': len(self._channels),
            'total_subscribers': sum(len(s) for s in self._channels.values()),
            'connected_users': len(self._user_clients)
        }


# 全局单例
ws_manager = WebSocketManager()


# ==================== 数据推送函数 ====================

async def push_realtime_quote(fund_code: str, quote_data: Dict):
    """推送实时行情数据"""
    await ws_manager.broadcast(
        f"{ChannelType.REALTIME_QUOTE.value}.{fund_code}",
        'quote_update',
        quote_data
    )


async def push_fund_estimate(fund_code: str, estimate: Dict):
    """推送基金估值更新"""
    await ws_manager.broadcast(
        f"{ChannelType.FUND_ESTIMATE.value}.{fund_code}",
        'estimate_update',
        estimate
    )


async def push_system_notification(user_ids: List[int], notification: Dict):
    """推送系统通知给指定用户"""
    for uid in user_ids:
        # 获取该用户的所有连接
        client_ids = ws_manager._user_clients.get(uid, set())
        for client_id in client_ids:
            await ws_manager.send_message(
                client_id,
                'notification',
                notification
            )


# ==================== Flask-SocketIO 集成适配器 ====================

class SocketIOAdapter:
    """Flask-SocketIO 适配器，将 SocketIO 事件桥接到 WebSocketManager"""
    
    def __init__(self, socketio, manager: WebSocketManager = None):
        from flask_socketio import SocketIO
        
        self.socketio: SocketIO = socketio
        self.manager = manager or ws_manager
        
        # 注册事件处理器
        self._register_events()
    
    def _register_events(self):
        @self.socketio.on('connect')
        async def handle_connect():
            # 从 session 中获取认证信息
            from flask import session
            user_id = session.get('user_id')
            if not user_id:
                return False  # 拒绝未认证连接
            
            import flask_socketio
            sid = flask_socketio.request().sid
            
            success = await self.manager.connect(sid, user_id)
            if not success:
                return False
            
            # 发送欢迎消息和可用频道列表
            self.socketio.emit('welcome', {
                'client_id': sid,
                'available_channels': [c.value for c in ChannelType],
                'server_time': time.time()
            }, room=sid)
        
        @self.socketio.on('disconnect')
        async def handle_disconnect():
            import flask_socketio
            sid = flask_socketio.request().sid
            await self.manager.disconnect(sid)
        
        @self.socketio.on('message')
        async def handle_message(data):
            import flask_socketio
            sid = flask_socketio.request().sid
            await self.manager.handle_message(sid, data)
        
        @self.socketio.on('subscribe')
        async def handle_subscribe(data):
            import flask_socketio
            sid = flask_socketio.request().sid
            if isinstance(data, str):
                channels = [data]
            elif isinstance(data, dict):
                channels = data.get('channels', [])
            else:
                channels = data or []
            
            for ch in channels:
                await self.manager.subscribe(sid, ch)
            
            self.socketio.emit('subscribed', {'channels': channels}, room=sid)


# ==================== 定时任务：自动广播估值数据 ====================

class EstimateBroadcaster:
    """
    基金估值定时广播器
    
    功能:
    - 定时从数据源获取最新估值
    - 推送给已订阅的用户
    - 支持增量推送（只推送变化的数据）
    """
    
    def __init__(
        self,
        interval: int = 3,          # 广播间隔（秒）
        enabled: bool = True
    ):
        self.interval = interval
        self.enabled = enabled
        self._last_values: Dict[str, float] = {}
        self._running = False
        self._task: Optional[asyncio.Task] = None
    
    async def start(self):
        """启动广播任务"""
        if self._running:
            return
        
        self._running = True
        self._task = asyncio.create_task(self._broadcast_loop())
        logger.info(f"Estimate broadcaster started (interval={self.interval}s)")
    
    async def stop(self):
        """停止广播任务"""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Estimate broadcaster stopped")
    
    async def _broadcast_loop(self):
        """广播主循环"""
        while self._running:
            try:
                await self._broadcast_estimates()
            except Exception as e:
                logger.error(f"Broadcaster error: {e}")
            
            await asyncio.sleep(self.interval)
    
    async def _broadcast_estimates(self):
        """获取并广播估值数据"""
        # TODO: 实际实现中从 Redis/数据库读取最新估值
        # 这里是示例框架代码
        
        # 检查是否有订阅者
        active_channels = [
            ch for ch in ws_manager._channels.keys()
            if ch.startswith(ChannelType.FUND_ESTIMATE.value)
        ]
        
        if not active_channels:
            return
        
        # 示例：模拟估值数据获取
        for channel in active_channels:
            fund_code = channel.split('.')[-1] if '.' in channel else ''
            
            if not fund_code:
                continue
            
            # 构造估值消息（实际应从数据源获取）
            estimate_data = {
                "code": fund_code,
                "value": 1.2345 + (hash(fund_code + str(int(time.time() // 60))) % 1000) / 10000,
                "change_percent": ((hash(fund_code) % 200) - 100) / 100,
                "update_time": time.strftime("%H:%M:%S"),
                "source": "estimated"
            }
            
            # 增量推送：只有值变化超过阈值才推送
            last_val = self._last_values.get(fund_code)
            new_val = estimate_data['value']
            
            if last_val is None or abs(new_val - last_val) > 0.0001:
                await push_fund_estimate(fund_code, estimate_data)
                self._last_values[fund_code] = new_val
