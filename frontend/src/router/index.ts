import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'
import NProgress from 'nprogress'

// 路由配置
const routes: RouteRecordRaw[] = [
  {
    path: '/',
    name: 'Home',
    component: () => import('@/views/HomeView.vue'),
    meta: { title: '首页', requiresAuth: false },
  },
  {
    path: '/fund-estimate',
    name: 'FundEstimate',
    component: () => import('@/views/FundEstimateView.vue'),
    meta: { title: '基金估算', icon: 'chart', requiresAuth: true },
  },
  {
    path: '/portfolio',
    name: 'Portfolio',
    component: () => import('@/views/PortfolioView.vue'),
    meta: { title: '组合分析', icon: 'portfolio', requiresAuth: true },
  },
  {
    path: '/realtime',
    name: 'RealTime',
    component: () => import('@/views/RealTimeView.vue'),
    meta: { title: '实时行情', icon: 'activity', requiresAuth: true },
  },
  {
    path: '/report',
    name: 'Report',
    component: () => import('@/views/ReportView.vue'),
    meta: { title: '报告中心', icon: 'document', requiresAuth: true },
  },
  {
    path: '/admin',
    name: 'Admin',
    component: () => import('@/views/AdminView.vue'),
    meta: { title: '系统管理', icon: 'settings', requiresAuth: true, role: 'admin' },
  },
  // 用户相关
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/auth/LoginView.vue'),
    meta: { title: '登录', guestOnly: true },
  },
  {
    path: '/register',
    name: 'Register',
    component: () => import('@/views/auth/RegisterView.vue'),
    meta: { title: '注册', guestOnly: true },
  },
  // 合规与站点信息（公开）
  {
    path: '/disclaimer',
    name: 'Disclaimer',
    component: () => import('@/views/legal/DisclaimerView.vue'),
    meta: { title: '免责声明', requiresAuth: false },
  },
  {
    path: '/privacy',
    name: 'Privacy',
    component: () => import('@/views/legal/PrivacyView.vue'),
    meta: { title: '隐私政策', requiresAuth: false },
  },
  {
    path: '/refund',
    name: 'Refund',
    component: () => import('@/views/legal/RefundView.vue'),
    meta: { title: '退款政策', requiresAuth: false },
  },
  {
    path: '/about',
    name: 'About',
    component: () => import('@/views/legal/AboutView.vue'),
    meta: { title: '关于我们', requiresAuth: false },
  },
  // 404
  {
    path: '/:pathMatch(.*)*',
    name: 'NotFound',
    component: () => import('@/views/NotFoundView.vue'),
    meta: { title: '页面不存在' },
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior(_to, _from, savedPosition) {
    if (savedPosition) return savedPosition
    return { top: 0, behavior: 'smooth' }
  },
})

// 全局前置守卫：权限控制 + 标题设置
router.beforeEach((to, _from, next) => {
  NProgress.start()

  // 设置页面标题
  const title = to.meta.title as string
  document.title = title ? `${title} | FUND-OS v5.0` : 'FUND-OS v5.0'

  // 认证检查
  const token = localStorage.getItem('token')
  const userStr = localStorage.getItem('user')
  let user = null
  try {
    user = userStr ? JSON.parse(userStr) : null
  } catch {
    // 解析失败则视为未登录
  }

  if (to.meta.requiresAuth && !token) {
    next({ name: 'Login', query: { redirect: to.fullPath } })
    return
  }

  if (to.meta.guestOnly && token) {
    next({ name: 'Home' })
    return
  }

  // 角色权限检查
  const requiredRole = to.meta.role as string
  if (requiredRole && user?.role !== requiredRole && user?.role !== 'admin') {
    next({ name: 'Home' })
    return
  }

  next()
})

router.afterEach(() => {
  NProgress.done()
})

export default router
