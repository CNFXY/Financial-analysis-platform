import { defineStore } from 'pinia'
import { ref } from 'vue'
import { get } from '@/utils/http'
import { SITE_CONFIG_DEFAULTS, type SiteConfig } from '@/config/site'

// 站点公开配置（备案号 / 联系方式等），供页脚与关于页使用。
// 数据权威来源为后端 /api/public/site-config；拉取失败时回退到前端默认值。
export const useSiteStore = defineStore('site', () => {
  const config = ref<SiteConfig>({ ...SITE_CONFIG_DEFAULTS })
  const loaded = ref(false)

  async function init() {
    try {
      const data = await get<Partial<SiteConfig>>('/public/site-config')
      if (data && typeof data === 'object') {
        config.value = { ...SITE_CONFIG_DEFAULTS, ...data }
      }
    } catch {
      config.value = { ...SITE_CONFIG_DEFAULTS }
    } finally {
      loaded.value = true
    }
  }

  return { config, loaded, init }
})
