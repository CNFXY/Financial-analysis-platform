import axios from 'axios'
import type { AxiosInstance, InternalAxiosRequestConfig, AxiosResponse } from 'axios'

// 创建 axios 实例
const http: AxiosInstance = axios.create({
  baseURL: '/api',
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
    'Accept': 'application/json',
  },
})

// 请求拦截器：自动附加 Token
http.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    const token = localStorage.getItem('token')
    if (token && config.headers) {
      config.headers.Authorization = `Bearer ${token}`
    }

    // 请求时间戳（防缓存）
    if (config.method === 'get') {
      config.params = { ...config.params, _t: Date.now() }
    }

    return config
  },
  (error) => Promise.reject(error)
)

// 响应拦截器：统一错误处理
http.interceptors.response.use(
  (response: AxiosResponse) => {
    const res = response.data
    // 业务层成功
    if (res.code === 0 || res.code === 200 || !('code' in res)) {
      return response
    }
    // 业务层错误
    const errMsg = res.message || '请求失败'
    handleBusinessError(res.code, errMsg)
    return Promise.reject(new Error(errMsg))
  },
  (error) => {
    if (error.response) {
      const { status } = error.response
      switch (status) {
        case 401:
          // Token 过期，跳转登录
          localStorage.removeItem('token')
          localStorage.removeItem('user')
          window.location.href = `/login?redirect=${encodeURIComponent(window.location.pathname)}`
          break
        case 403:
          console.error('无权限访问')
          break
        case 404:
          console.error('接口不存在')
          break
        case 429:
          console.error('请求过于频繁')
          break
        case 500:
          console.error('服务器内部错误')
          break
        default:
          console.error(`HTTP ${status}: ${error.message}`)
      }
      // 返回服务端错误信息
      const serverMsg = error.response.data?.message || error.message
      error.message = serverMsg
    } else if (error.code === 'ECONNABORTED') {
      error.message = '请求超时，请稍后重试'
    } else if (!window.navigator.onLine) {
      error.message = '网络连接已断开，请检查网络'
    }
    return Promise.reject(error)
  }
)

function handleBusinessError(code: number, message: string) {
  switch (code) {
    case 401001:
      localStorage.removeItem('token')
      window.location.href = '/login'
      break
    case 403003:
      console.warn('权限不足:', message)
      break
    default:
      console.warn(`业务错误 [${code}]:`, message)
  }
}

export default http

// 导出便捷方法
export function get<T = any>(url: string, params?: Record<string, any>): Promise<T> {
  return http.get(url, { params }).then(r => r.data)
}

export function post<T = any>(url: string, data?: any): Promise<T> {
  return http.post(url, data).then(r => r.data)
}

export function put<T = any>(url: string, data?: any): Promise<T> {
  return http.put(url, data).then(r => r.data)
}

export function del<T = any>(url: string): Promise<T> {
  return http.delete(url).then(r => r.data)
}
