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

interface KLineDataItem {
  date: string
  open: number
  high: number
  low: number
  close: number
  volume?: number
}

type KLineData = KLineDataItem

interface Props {
  data: KLineData[]
  height?: string
  loading?: boolean
  showMA?: boolean
  maPeriods?: number[]
}

const props = withDefaults(defineProps<Props>(), {
  height: '500px',
  loading: false,
  showMA: true,
  maPeriods: () => [5, 10, 20, 60]
})

// 计算移动平均线
function calculateMA(data: KLineData[], dayCount: number): (number | null)[] {
  const result: (number | null)[] = []
  for (let i = 0; i < data.length; i++) {
    if (i < dayCount - 1) {
      result.push(null)
      continue
    }
    let sum = 0
    for (let j = 0; j < dayCount; j++) {
      sum += data[i - j].close
    }
    result.push(sum / dayCount)
  }
  return result
}

const chartOption = computed(() => {
  const dates = props.data.map(d => d.date)
  
  // K线数据 [open, close, lowest, highest]
  const klineData = props.data.map(d => [d.open, d.close, d.low, d.high])
  // 成交量数据
  const volumeData = props.data.map(d => d.volume || 0)
  
  // MA 线数据
  const series: any[] = [
    {
      type: 'candlestick',
      name: 'K线',
      data: klineData,
      itemStyle: {
        color: '#ef4444',      // 涨 - 红
        color0: '#22c55e',     // 跌 - 绿
        borderColor: '#ef4444',
        borderColor0: '#22c55e',
        borderWidth: 1
      },
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'cross' },
        formatter: (params: any) => {
          if (!Array.isArray(params)) return ''
          const p = params[0] as { axisValue: string; value: number[] }
          const idx = props.data.findIndex(d => d.date === p.axisValue)
          if (idx === -1) return ''
          const item = props.data[idx]
          return `
            <div class="text-sm">
              <div class="font-bold">${item.date}</div>
              <div>开: ${item.open.toFixed(4)}</div>
              <div>收: ${item.close.toFixed(4)}</div>
              <div>高: ${item.high.toFixed(4)}</div>
              <div>低: ${item.low.toFixed(4)}</div>
              ${item.volume ? `<div>成交量: ${(item.volume / 10000).toFixed(2)}万</div>` : ''}
            </div>
          `.trim()
        }
      }
    }
  ]
  
  // 移动平均线
  if (props.showMA) {
    props.maPeriods.forEach(period => {
      const maData = calculateMA(props.data, period)
      const colors: Record<number, string> = { 5: '#f59e0b', 10: '#3b82f6', 20: '#8b5cf6', 60: '#ec4899' }
      series.push({
        name: `MA${period}`,
        type: 'line',
        data: maData,
        smooth: true,
        symbol: 'none',
        lineStyle: { width: 1.5, color: colors[period] || '#888' },
        z: 10 + period
      })
    })
  }
  
  return {
    animation: true,
    animationDuration: 1000,
    legend: {
      data: ['K线', ...props.maPeriods.map(p => `MA${p}`)],
      textStyle: { color: '#9ca3af', fontSize: 12 },
      top: 10
    },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'cross' },
      backgroundColor: 'rgba(17, 24, 39, 0.95)',
      borderColor: '#374151',
      textStyle: { color: '#f9fafb' }
    },
    grid: [
      {
        left: '8%',
        right: '8%',
        top: '15%',
        height: '55%'
      },
      {
        left: '8%',
        right: '8%',
        top: '75%',
        height: '18%'
      }
    ],
    xAxis: [
      {
        type: 'category',
        data: dates,
        boundaryGap: false,
        axisLine: { lineStyle: { color: '#4b5563' } },
        axisLabel: { color: '#9ca3af' },
        splitArea: { show: false }
      },
      {
        type: 'category',
        gridIndex: 1,
        data: dates,
        axisLine: { lineStyle: { color: '#4b5563' } },
        axisLabel: { show: false }
      }
    ],
    yAxis: [
      {
        scale: true,
        splitArea: { show: false },
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: {
          color: '#9ca3af',
          formatter: '{value}'
        },
        splitLine: { lineStyle: { color: '#1f2937', type: 'dashed' } }
      },
      {
        scale: true,
        gridIndex: 1,
        splitNumber: 2,
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: { show: false },
        splitLine: { show: false }
      }
    ],
    dataZoom: [
      {
        type: 'inside',
        xAxisIndex: [0, 1],
        start: 70,
        end: 100
      },
      {
        type: 'slider',
        xAxisIndex: [0, 1],
        start: 70,
        end: 100,
        height: 20,
        bottom: 10,
        borderColor: '#374151',
        fillerColor: 'rgba(59, 130, 246, 0.15)',
        handleStyle: { color: '#3b82f6' },
        textStyle: { color: '#9ca3af' }
      }
    ],
    series: [...series, {
      name: '成交量',
      type: 'bar',
      xAxisIndex: 1,
      yAxisIndex: 1,
      data: volumeData.map((v, i) => ({
        value: v,
        itemStyle: {
          color: props.data[i].close >= props.data[i].open ? 'rgba(239, 68, 68, 0.5)' : 'rgba(34, 197, 94, 0.5)'
        }
      }))
    }],
    backgroundColor: 'transparent'
  } as EChartsOption
})
</script>
