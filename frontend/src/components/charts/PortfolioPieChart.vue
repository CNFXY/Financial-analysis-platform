<template>
  <BaseChart
    :option="chartOption"
    :height="height"
    :loading="loading"
  />
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { EChartsOption } from 'echarts'
import BaseChart from './BaseChart.vue'

interface PortfolioItem {
  name: string
  value: number
  percentage?: number
  color?: string
  category?: string
}

interface Props {
  data: PortfolioItem[]
  height?: string
  loading?: boolean
  type?: 'pie' | 'rose' | 'treemap'
  showLegend?: boolean
  showLabel?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  height: '400px',
  loading: false,
  type: 'pie',
  showLegend: true,
  showLabel: true
})

// 预设颜色方案（FUND-OS 品牌色）
const COLORS = [
  '#3b82f6', // blue-500
  '#22c55e', // green-500
  '#f59e0b', // amber-500
  '#ef4444', // red-500
  '#8b5cf6', // violet-500
  '#ec4899', // pink-500
  '#06b6d4', // cyan-500
  '#f97316', // orange-500
  '#14b8a6', // teal-500
  '#a855f7'  // purple-500
]

const chartOption = computed(() => {
  const chartData = props.data.map((item, index) => ({
    name: item.name,
    value: item.value,
    itemStyle: {
      color: item.color || COLORS[index % COLORS.length],
      borderRadius: props.type === 'pie' ? 8 : 2,
      borderColor: 'rgba(255,255,255,0.1)',
      borderWidth: 2
    }
  }))
  
  const baseSeries = {
    type: props.type === 'treemap' ? 'treemap' : 'pie',
    radius: props.type === 'rose' ? ['20%', '70%'] : ['40%', '70%'],
    center: props.showLegend ? ['45%', '55%'] : ['50%', '55%'],
    data: chartData,
    label: {
      show: props.showLabel,
      formatter: (params: any) => {
        return `${params.name}\n${params.percent.toFixed(1)}%`
      },
      fontSize: 12,
      color: '#f9fafb'
    },
    emphasis: {
      label: { show: true, fontWeight: 'bold', fontSize: 14 },
      itemStyle: {
        shadowBlur: 10,
        shadowOffsetX: 0,
        shadowColor: 'rgba(0, 0, 0, 0.3)',
        borderWidth: 0
      }
    },
    animationType: 'scale',
    animationEasing: 'elasticOut',
    animationDelay: (idx: number) => idx * 100
  }
  
  if (props.type === 'rose') {
    Object.assign(baseSeries, {
      roseType: 'area',
      itemStyle: { borderRadius: 6 }
    })
  }
  
  if (props.type === 'treemap') {
    delete (baseSeries as Record<string, unknown>).radius
    delete (baseSeries as Record<string, unknown>).center
    ;(baseSeries as Record<string, unknown>).visibleMin = 100
  }
  
  return {
    tooltip: {
      trigger: 'item',
      backgroundColor: 'rgba(17, 24, 39, 0.95)',
      borderColor: '#374151',
      textStyle: { color: '#f9fafb' },
      formatter: (params: any) => {
        const item = props.data.find(d => d.name === params.name)
        return `
          <div class="text-sm p-2">
            <div class="font-bold mb-1">${params.marker} ${params.name}</div>
            <div>金额: ¥${params.value.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}</div>
            <div>占比: ${params.percent.toFixed(2)}%</div>
            ${item?.category ? `<div class="text-gray-400 mt-1">分类: ${item.category}</div>` : ''}
          </div>
        `.trim()
      }
    },
    legend: {
      show: props.showLegend,
      orient: 'vertical',
      right: '5%',
      top: 'center',
      textStyle: { color: '#9ca3af', fontSize: 12 },
      itemWidth: 12,
      itemHeight: 12,
      itemGap: 12,
      icon: 'roundRect',
      formatter: (name: string) => {
        const item = props.data.find(d => d.name === name)
        const pct = item?.percentage || (item ? ((item.value / props.data.reduce((s, d) => s + d.value, 0)) * 100) : 0)
        return `${name}  ${pct.toFixed(1)}%`
      }
    },
    series: [baseSeries] as unknown[],
    backgroundColor: 'transparent',
    graphic: [
      {
        type: 'text',
        left: props.showLegend ? '30%' : 'center',
        top: '42%',
        style: {
          text: `总计\n¥${props.data.reduce((s, d) => s + d.value, 0).toLocaleString('zh-CN', { minimumFractionDigits: 2 })}`,
          textAlign: 'center',
          fill: '#d1d5db',
          fontSize: 14,
          lineHeight: 22
        }
      }
    ]
  } as EChartsOption
})
</script>
