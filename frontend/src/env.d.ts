/// <reference types="vite/client" />

declare module '*.vue' {
  import type { DefineComponent } from 'vue'
  const component: DefineComponent<{}, {}, any>
  export default component
}

// API 响应类型
export interface ApiResponse<T = any> {
  code: number
  message: string
  data: T
  timestamp: number
}

export interface PaginatedResponse<T> {
  items: T[]
  total: number
  page: number
  pageSize: number
  totalPages: number
}

// 基金相关类型
export interface FundInfo {
  code: string
  name: string
  type: string
  nav?: number
  estimatedNav?: number
  changePercent?: number
  date?: string
}

export interface PortfolioItem {
  fundCode: string
  shares: number
  costPrice?: number
  currentNav?: number
  profit?: number
  profitRate?: number
}

// 用户相关
export interface User {
  id: string
  username: string
  email?: string
  role: 'admin' | 'user' | 'viewer'
  avatar?: string
  createdAt: string
  subscription?: SubscriptionInfo
}

export interface SubscriptionInfo {
  plan: 'free' | 'basic' | 'pro' | 'enterprise'
  expiresAt: string
  quotaUsed: number
  quotaLimit: number
}
