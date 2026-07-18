<template>
  <div ref="chartRef" class="w-full h-full min-h-[300px]" />
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch, computed } from 'vue'
import * as echarts from 'echarts'
import type { EChartsOption } from 'echarts'
import 'echarts/theme/dark'

interface Props {
  option?: EChartsOption
  theme?: string | object
  autoResize?: boolean
  loading?: boolean
  height?: string
}

const props = withDefaults(defineProps<Props>(), {
  theme: 'dark',
  autoResize: true,
  loading: false,
  height: undefined
})

const emit = defineEmits<{
  (e: 'click', params: unknown): void
  (e: 'rendered'): void
}>()

const chartRef = ref<HTMLDivElement>()
let chartInstance: echarts.ECharts | null = null

// 响应式尺寸
const chartStyle = computed(() => ({
  height: props.height || '100%'
}))

// 初始化图表
function initChart() {
  if (!chartRef.value) return
  
  // 如果已有实例先销毁
  destroyChart()
  
  chartInstance = echarts.init(chartRef.value, props.theme, {
    renderer: 'canvas',
    locale: 'ZH'
  })
  
  // 点击事件
  chartInstance.on('click', (params) => {
    emit('click', params)
  })
  
  // 设置选项
  if (props.option) {
    chartInstance.setOption(props.option, true)
  }
  
  emit('rendered')
}

// 销毁实例
function destroyChart() {
  if (chartInstance) {
    chartInstance.dispose()
    chartInstance = null
  }
}

// 监听选项变化
watch(
  () => props.option,
  (newOption) => {
    if (chartInstance && newOption) {
      chartInstance.setOption(newOption, true)
    }
  },
  { deep: true }
)

// 加载状态
watch(() => props.loading, (loading) => {
  if (chartInstance) {
    if (loading) {
      chartInstance.showLoading()
    } else {
      chartInstance.hideLoading()
    }
  }
})

// 窗口大小变化处理
function handleResize() {
  chartInstance?.resize()
}

onMounted(() => {
  initChart()
  
  if (props.autoResize) {
    window.addEventListener('resize', handleResize)
  }
})

onUnmounted(() => {
  window.removeEventListener('resize', handleResize)
  destroyChart()
})

// 暴露方法给父组件
defineExpose({
  getInstance: () => chartInstance,
  refresh: () => chartInstance?.setOption(props.option || {}, true),
  resize: handleResize,
  downloadImage: () => chartInstance?.getDataURL({ type: 'png' })
})
</script>
