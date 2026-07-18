<template>
  <BaseChart
    :option="chartOption"
    :height="height"
    :loading="loading"
  />
</template>

<script setup lang="ts">
import { computed, ref, watch, onUnmounted } from 'vue'
import * as echarts from 'echarts'
import BaseChart from './BaseChart.vue'

interface QuotePoint {
  time: string
  price: number
  volume?: number
  avgPrice?: number
}

interface Props {
  data: QuotePoint[]
  height?: string
  loading?: boolean
  updateInterval?: number // 自动刷新间隔（毫秒）
}

const props = withDefaults(defineProps<Props>(), {
  height: '350px',
  loading: false,
  updateInterval: 0
})

// 最新价格引用（用于实时闪烁效果）
const latestPrice = ref<number | null>(null)

// 监听数据变化更新最新价（避免在 computed 中产生副作用）
watch(
  () => props.data,
  (data) => {
    latestPrice.value = data.length > 0 ? data[data.length - 1].price : null
  },
  { immediate: true }
)

const chartOption = computed(() => {
  const times = props.data.map(d => d.time)
  const prices = props.data.map(d => d.price)
  
  const firstPrice = prices[0] || 0
  const lastPrice = latestPrice.value || 0
  const priceChange = lastPrice - firstPrice
  const changePercent = firstPrice !== 0 ? (priceChange / firstPrice * 100) : 0
  
  // 涨跌颜色
  const trendColor = changePercent >= 0 ? '#ef4444' : '#22c55e'
  
  return {
    title: {
      text: '',
      left: 'left',
      top: 5,
      textStyle: { color: '#9ca3af', fontSize: 12 },
      subtext: `最新: ${lastPrice.toFixed(4)}  `,
      subtextStyle: {
        color: trendColor,
        fontSize: 18,
        fontWeight: 'bold',
        rich: {
          change: {
            color: trendColor,
            fontSize: 14,
            padding: [0, 8]
          }
        },
        formatter: () => `${lastPrice.toFixed(4)}`
      }
    },
    tooltip: {
      trigger: 'axis',
      backgroundColor: 'rgba(17, 24, 39, 0.95)',
      borderColor: '#374151',
      textStyle: { color: '#f9fafb' },
      formatter(params: unknown[]) {
        if (!Array.isArray(params)) return ''
        const p = params[0] as { axisValue?: string; value?: number; dataIndex?: number }
        const idx = p.dataIndex ?? 0
        const item = props.data[idx]
        return `
          <div class="text-sm">
            <b>${p.axisValue}</b><br/>
            价格: ${item?.price?.toFixed(4)}<br/>
            ${item?.volume ? `成交量: ${item.volume}` : ''}
          </div>
        `.trim()
      }
    },
    legend: {
      data: ['价格', ...(props.data.some(d => d.avgPrice) ? ['均价'] : [])],
      textStyle: { color: '#9ca3af' },
      top: props.data.some(d => d.avgPrice) ? 35 : 30,
      right: 10
    },
    grid: {
      left: '3%',
      right: '4%',
      bottom: '15%',
      top: props.data.some(d => d.avgPrice) ? '20%' : '15%',
      containLabel: true
    },
    xAxis: {
      type: 'category',
      boundaryGap: false,
      data: times,
      axisLine: { lineStyle: { color: '#4b5563' } },
      axisLabel: { 
        color: '#9ca3af',
        rotate: props.data.length > 20 ? 45 : 0,
        fontSize: 11
      }
    },
    yAxis: {
      type: 'value',
      scale: true,
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: '#9ca3af', formatter: '{value}' },
      splitLine: { lineStyle: { color: '#1f2937', type: 'dashed' } },
      min: (value: { min: number }) => value.min * 0.998,
      max: (value: { max: number }) => value.max * 1.002
    },
    series: [
      // 主价格线
      {
        name: '价格',
        type: 'line',
        smooth: true,
        symbol: 'none',
        step: false,
        data: prices,
        lineStyle: {
          width: 2,
          color: new echarts.graphic.LinearGradient(0, 0, 1, 0, [
            { offset: 0, color: '#3b82f6' },
            { offset: 1, color: '#06b6d4' }
          ])
        },
        areaStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: changePercent >= 0 ? 'rgba(239, 68, 68, 0.25)' : 'rgba(34, 197, 94, 0.25)' },
            { offset: 1, color: 'rgba(17, 24, 39, 0)' }
          ])
        },
        markLine: {
          silent: true,
          symbol: 'none',
          data: [
            {
              yAxis: firstPrice,
              label: { formatter: '开盘', color: '#9ca3af', fontSize: 10 },
              lineStyle: { color: '#6b7280', type: 'dashed' }
            },
            {
              yAxis: Math.max(...prices),
              label: { formatter: '最高', color: '#ef4444', fontSize: 10 },
              lineStyle: { color: '#ef4444', type: 'dotted' }
            },
            {
              yAxis: Math.min(...prices),
              label: { formatter: '最低', color: '#22c55e', fontSize: 10 },
              lineStyle: { color: '#22c55e', type: 'dotted' }
            }
          ]
        },
        markPoint: {
          data: [
            {
              type: 'max',
              name: '最高',
              symbol: 'triangle',
              symbolSize: 10,
              itemStyle: { color: '#ef4444' }
            },
            {
              type: 'min',
              name: '最低',
              symbol: 'triangle',
              symbolSize: 10,
              itemStyle: { color: '#22c55e' },
              symbolRotate: 180
            }
          ],
          label: { show: false }
        },
        animationDuration: 300,
        animationEasingUpdate: 'linear'
      },
      // 均价线（如果有）
      ...(props.data.some(d => d.avgPrice) ? [{
        name: '均价',
        type: 'line' as const,
        smooth: true,
        symbol: 'none',
        data: props.data.map(d => d.avgPrice ?? null),
        lineStyle: { width: 1.5, color: '#f59e0b', type: 'dashed' }
      }] : [])
    ],
    backgroundColor: 'transparent'
  } as import('echarts').EChartsOption
})
</script>
