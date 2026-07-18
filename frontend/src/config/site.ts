// 站点与合规配置（前端兜底默认值）
// 真实值由后端 /api/public/site-config 返回（源自 config.py / 环境变量）。
// 当后端不可达时，前端回退到此处默认值，保证页脚与关于页始终可渲染。

export interface SiteConfig {
  site_name: string
  company_name: string
  icp_beian: string
  police_beian: string
  contact_email: string
  service_tel: string
}

export const SITE_CONFIG_DEFAULTS: SiteConfig = {
  site_name: 'FUND-OS 智能基金估算系统',
  company_name: '请填写运营主体公司全称',
  icp_beian: '',
  police_beian: '',
  contact_email: 'support@example.com',
  service_tel: '',
}
