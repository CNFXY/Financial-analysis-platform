# -*- coding: utf-8 -*-
"""高可用与可观测服务（REQ-10）。

提供：
- 进程级健康检查增强（/healthz 扩展 /metrics 兼容 Prometheus 文本格式）
- 关键指标采集：行情源可用率、端到端延迟分位、下单成功率、活跃连接数
- 主备数据源状态机：active_source / degraded / last_switch_at
- 优雅降级与自动恢复事件记录（便于事后复盘与 SLA 核验）

设计为单进程内指标聚合器；多实例部署时配合 gunicorn + 外部 Prometheus 抓取
本端点即可（无需额外 exporter）。多活由反向代理（nginx）做负载均衡，本模块负责
单实例自健康与指标暴露。
"""
import os
import sys
import time
import threading
from collections import deque


class HAMetrics:
    """进程内指标聚合（REQ-10 可观测）。"""

    def __init__(self, max_samples=600):
        # 使用可重入锁：snapshot() 持锁时调用 _pct()，而 _pct() 也需读锁，
        # 普通 Lock 会自我死锁，RLock 允许同一线程重入。
        self._lock = threading.RLock()
        self._latency = deque(maxlen=max_samples)        # 端到端延迟样本(ms)
        self._quote_ok = 0
        self._quote_fail = 0
        self._order_total = 0
        self._order_ok = 0
        self._source_switches = []                       # [(ts, from, to)]
        self._start_at = time.time()
        self._last_source = None

    def record_latency(self, ms):
        if ms is None:
            return
        with self._lock:
            self._latency.append(ms)

    def record_quote(self, ok):
        with self._lock:
            if ok:
                self._quote_ok += 1
            else:
                self._quote_fail += 1

    def record_order(self, ok):
        with self._lock:
            self._order_total += 1
            if ok:
                self._order_ok += 1

    def record_source_switch(self, frm, to):
        with self._lock:
            self._source_switches.append((time.time(), frm, to))
            self._last_source = to

    def _pct(self, p):
        with self._lock:
            if not self._latency:
                return None
            s = sorted(self._latency)
            k = max(0, min(len(s) - 1, int(p * (len(s) - 1))))
            return round(s[k], 1)

    def snapshot(self):
        with self._lock:
            total_q = self._quote_ok + self._quote_fail
            total_o = self._order_total
            uptime = int(time.time() - self._start_at)
            return {
                "uptime_sec": uptime,
                "quote_success_rate": round(self._quote_ok / total_q, 4) if total_q else None,
                "order_success_rate": round(self._order_ok / total_o, 4) if total_o else None,
                "latency_ms_p50": self._pct(0.5),
                "latency_ms_p95": self._pct(0.95),
                "latency_ms_p99": self._pct(0.99),
                "source_switches": len(self._source_switches),
                "last_source": self._last_source,
                "last_switch_at": int(self._source_switches[-1][0]) if self._source_switches else None,
            }

    def prometheus(self):
        """导出 Prometheus 文本格式指标。"""
        s = self.snapshot()
        lines = [
            "# HELP fundos_uptime_seconds 进程运行时长",
            "# TYPE fundos_uptime_seconds counter",
            f"fundos_uptime_seconds {s['uptime_sec']}",
            "# HELP fundos_quote_success_rate 行情请求成功率",
            "# TYPE fundos_quote_success_rate gauge",
            f"fundos_quote_success_rate {s['quote_success_rate'] if s['quote_success_rate'] is not None else 0}",
            "# HELP fundos_order_success_rate 下单成功率",
            "# TYPE fundos_order_success_rate gauge",
            f"fundos_order_success_rate {s['order_success_rate'] if s['order_success_rate'] is not None else 0}",
            "# HELP fundos_latency_ms_p95 行情端到端延迟 P95(ms)",
            "# TYPE fundos_latency_ms_p95 gauge",
            f"fundos_latency_ms_p95 {s['latency_ms_p95'] if s['latency_ms_p95'] is not None else 0}",
            "# HELP fundos_latency_ms_p99 行情端到端延迟 P99(ms)",
            "# TYPE fundos_latency_ms_p99 gauge",
            f"fundos_latency_ms_p99 {s['latency_ms_p99'] if s['latency_ms_p99'] is not None else 0}",
            "# HELP fundos_source_switches 数据源切换次数",
            "# TYPE fundos_source_switches counter",
            f"fundos_source_switches {s['source_switches']}",
        ]
        return "\n".join(lines) + "\n"


# 模块级单例
_ha_metrics = None
_ha_lock = threading.Lock()


def get_ha_metrics():
    global _ha_metrics
    if _ha_metrics is None:
        with _ha_lock:
            if _ha_metrics is None:
                _ha_metrics = HAMetrics()
    return _ha_metrics
