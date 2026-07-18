"""
FUND-OS 统一日志系统 v5.0
结构化 JSON 日志 + ELK/Sentry 集成
"""

import os
import sys
import logging
import json
import traceback
from datetime import datetime, timezone
from typing import Any, Optional


class JsonFormatter(logging.Formatter):
    """结构化 JSON 日志格式化器"""

    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno,
        }

        # 附加字段
        if hasattr(record, 'user_id'):
            log_data['user_id'] = record.user_id
        if hasattr(record, 'request_id'):
            log_data['request_id'] = record.request_id
        if hasattr(record, 'ip'):
            log_data['ip'] = record.ip

        # 异常信息
        if record.exc_info:
            log_data['exception'] = {
                'type': record.exc_info[0].__name__,
                'message': str(record.exc_info[1]),
                'traceback': traceback.format_exception(*record.exc_info),
            }

        return json.dumps(log_data, ensure_ascii=False, default=str)


def setup_logging(
    level: str = 'INFO',
    log_file: Optional[str] = None,
    json_format: bool = True,
) -> logging.Logger:
    """
    初始化全局日志配置

    Args:
        level: 日志级别 (DEBUG / INFO / WARNING / ERROR)
        log_file: 日志文件路径（可选）
        json_format: 是否使用 JSON 格式（ELK 集成时建议开启）
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # 清除已有 handler
    for h in root_logger.handlers[:]:
        root_logger.removeHandler(h)

    # 控制台输出
    console_handler = logging.StreamHandler(sys.stdout)
    if json_format:
        console_handler.setFormatter(JsonFormatter())
    else:
        console_handler.setFormatter(
            logging.Formatter(
                '%(asctime)s [%(levelname)s] %(name)s - %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
        )
    root_logger.addHandler(console_handler)

    # 文件输出
    if log_file:
        os.makedirs(os.path.dirname(log_file) or '.', exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setFormatter(JsonFormatter())
        file_handler.setLevel(logging.DEBUG)
        root_logger.addHandler(file_handler)

    # 降低第三方库日志级别
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('werkzeug').setLevel(logging.WARNING)
    logging.getLogger('matplotlib').setLevel(logging.WARNING)

    logger = logging.getLogger('fund-os')
    logger.info(f'日志系统初始化完成 (level={level}, json={json_format})')
    return logger


# 全局 Logger 实例
logger = logging.getLogger('fund-os')


def log_request(request_id: str, method: str, path: str,
                status_code: int, duration_ms: float,
                user_id: str = '', ip: str = ''):
    """记录 API 请求日志"""
    extra = {
        'request_id': request_id,
        'user_id': user_id,
        'ip': ip,
    }
    msg = f'{method} {path} → {status_code} ({duration_ms:.1f}ms)'

    if status_code >= 500:
        logger.error(msg, extra=extra)
    elif status_code >= 400:
        logger.warning(msg, extra=extra)
    else:
        logger.info(msg, extra=extra)


def log_error(error: Exception, context: dict[str, Any] | None = None):
    """记录错误详情"""
    data = {
        'error_type': type(error).__name__,
        'error_message': str(error),
        **(context or {}),
    }
    logger.error(json.dumps(data, ensure_ascii=False), exc_info=error)
