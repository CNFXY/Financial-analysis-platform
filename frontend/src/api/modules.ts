/**
 * FUND-OS API 模块定义
 * RESTful 规范化接口层
 */

import { get, post, put, del } from '@/utils/http'
import type { ApiResponse, PaginatedResponse, FundInfo, PortfolioItem } from '@/env'

// ==================== 认证模块 ====================
export const authApi = {
  login: (data: { username: string; password: string }) =>
    post<ApiResponse<{ token: string; user: any }>>('/auth/login', data),

  register: (data: { username: string; email: string; password: string }) =>
    post<ApiResponse<{ token: string; user: any }>>('/auth/register', data),

  logout: () => post<ApiResponse>('/auth/logout'),

  getProfile: () => get<ApiResponse<any>>('/auth/profile'),

  refresh: (refreshToken: string) =>
    post<ApiResponse<{ token: string }>>('/auth/refresh', { refreshToken }),
}

// ==================== 基金估算模块 ====================
export const fundApi = {
  // 搜索基金
  search: (keyword: string) =>
    get<ApiResponse<FundInfo[]>>('/fund/search', { keyword }),

  // 获取基金详情
  getDetail: (code: string) =>
    get<ApiResponse<FundInfo & { holdings: any[]; history: any[] }>>(`/fund/${code}`),

  // 执行估值估算
  estimate: (codes: string[]) =>
    post<ApiResponse<any[]>>('/fund/estimate', { codes }),

  // 获取估值历史
  getEstimateHistory: (code: string, days = 30) =>
    get<ApiResponse<any[]>>(`/fund/${code}/history`, { days }),
}

// ==================== 投资组合模块 ====================
export const portfolioApi = {
  // 获取用户所有组合
  list: () => get<ApiResponse<any[]>>('/portfolio'),

  // 创建组合
  create: (data: { name: string; items: PortfolioItem[] }) =>
    post<ApiResponse<any>>('/portfolio', data),

  // 更新组合
  update: (id: string, data: Partial<{ name: string; items: PortfolioItem[] }>) =>
    put<ApiResponse>(`/portfolio/${id}`, data),

  // 删除组合
  remove: (id: string) => del<ApiResponse>(`/portfolio/${id}`),

  // 计算组合分析数据
  analyze: (items: PortfolioItem[]) =>
    post<ApiResponse<{
      totalValue: number; totalCost: number
      profit: number; profitRate: number
      riskMetrics: any; allocation: any[]
    }>>('/portfolio/analyze', { items }),
}

// ==================== 实时行情模块 ====================
export const realtimeApi = {
  // 获取行情快照（支持 WebSocket 推送）
  snapshot: (symbols: string[]) =>
    get<ApiResponse<any[]>>('/realtime/snapshot', { symbols: symbols.join(',') }),

  // K 线数据
  kline: (symbol: string, period: string, limit = 100) =>
    get<ApiResponse<any[]>>(`/realtime/kline/${symbol}`, { period, limit }),

  // 自选列表
  watchlist: {
    get: () => get<ApiResponse<string[]>>('/realtime/watchlist'),
    add: (symbols: string[]) => post<ApiResponse>('/realtime/watchlist/add', { symbols }),
    remove: (symbols: string[]) => post<ApiResponse>('/realtime/watchlist/remove', { symbols }),
  },

  // 告警规则
  alerts: {
    list: () => get<ApiResponse<any[]>>('/realtime/alerts'),
    create: (rule: any) => post<ApiResponse>('/realtime/alerts', rule),
    delete: (id: string) => del<ApiResponse>(`/realtime/alerts/${id}`),
  },
}

// ==================== 报告模块 ====================
export const reportApi = {
  // 获取报告列表
  list: (page = 1, pageSize = 10) =>
    get<PaginatedResponse<any>>('/report/list', { page, pageSize }),

  // 生成日报
  generateDaily: () => post<ApiResponse<{ id: string; url: string }>>('/report/daily/generate'),

  // 生成组合报告
  generatePortfolioReport: (portfolioId: string) =>
    post<ApiResponse<{ id: string; url: string }>>('/report/portfolio/generate', { portfolioId }),

  // 导出 Excel
  exportExcel: (reportId: string) =>
    get<Blob>(`/report/${reportId}/export`),
}

// ==================== 管理后台模块 ====================
export const adminApi = {
  // 用户管理
  users: {
    list: (page = 1, pageSize = 20) =>
      get<PaginatedResponse<any>>('/admin/users', { page, pageSize }),
    updateRole: (userId: string, role: string) =>
      put<ApiResponse>(`/admin/users/${userId}/role`, { role }),
  },

  // 系统配置
  config: {
    get: () => get<ApiResponse<Record<string, any>>>('/admin/config'),
    update: (config: Record<string, any>) =>
      put<ApiResponse>('/admin/config', config),
  },

  // 系统监控
  metrics: () => get<ApiResponse<any>>('/admin/metrics'),
  logs: (page = 1, level?: string) =>
    get<PaginatedResponse<any>>('/admin/logs', { page, level }),
}
