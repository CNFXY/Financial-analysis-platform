<script setup lang="ts">
import { storeToRefs } from 'pinia'
import LegalPage from '@/components/legal/LegalPage.vue'
import { useSiteStore } from '@/stores/site'

const siteStore = useSiteStore()
const { config } = storeToRefs(siteStore)
</script>

<template>
  <LegalPage title="关于我们" updated="2026-07-18">
    <p>{{ config.site_name }} 是一站式基金净值估算、组合分析与实时行情平台，致力于以量化模型与可视化工具，帮助投资者更高效地理解基金表现与市场动态。</p>

    <h2>一、我们的服务</h2>
    <ul>
      <li>基金净值估算与多维度对比；</li>
      <li>组合分析、风险评测与回测；</li>
      <li>实时行情、自选与预警；</li>
      <li>面向专业投资者的付费订阅能力。</li>
    </ul>

    <h2>二、运营主体</h2>
    <p>运营主体：{{ config.company_name || '请填写运营主体公司全称' }}</p>
    <p v-if="config.service_tel">客服电话：{{ config.service_tel }}</p>
    <p v-if="config.contact_email">联系邮箱：<a :href="`mailto:${config.contact_email}`">{{ config.contact_email }}</a></p>

    <h2>三、备案信息</h2>
    <ul>
      <li v-if="config.icp_beian">ICP 备案号：<a href="https://beian.miit.gov.cn/" target="_blank" rel="noopener">{{ config.icp_beian }}</a></li>
      <li v-if="config.police_beian">公安备案号：{{ config.police_beian }}</li>
      <li v-if="!config.icp_beian && !config.police_beian" class="text-gray-500">备案信息待运营方补全后公示。</li>
    </ul>

    <h2>四、合规与责任</h2>
    <p>本系统所提供内容仅供研究与参考，不构成投资建议。投资有风险，入市需谨慎。更多请参见《免责声明》《隐私政策》与《退款政策》。</p>
  </LegalPage>
</template>
