import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'
import { useSiteStore } from '@/stores/site'

// 全局样式
import './styles/index.css'

// NProgress 进度条
import 'nprogress/nprogress.css'
import NProgress from 'nprogress'
NProgress.configure({ showSpinner: false, trickleSpeed: 100 })

const app = createApp(App)
const pinia = createPinia()

app.use(pinia)
app.use(router)

// 初始化站点公开配置（备案号 / 联系方式等，供页脚与关于页使用）
useSiteStore().init()

// 路由切换进度条
router.beforeEach(() => {
  NProgress.start()
})
router.afterEach(() => {
  NProgress.done()
})

app.mount('#app')
