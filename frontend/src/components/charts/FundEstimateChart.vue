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

interface EstimationPoint {
  date: string
  estimatedValue: number
  actualValue?: number
  upperConfidence?: number
  lowerConfidence?: number
}

interface Props {
  data: EstimationPoint[]
  height?: string
  loading?: boolean
  showConfidence?: boolean
  title?: string
  unit?: string
}

const props = withDefaults(defineProps<Props>(), {
  height: '400px',
  loading: false,
  showConfidence: true,
  title: '基金估值走势',
  unit: ''
})

const chartOption = computed(() => {
  const dates = props.data.map(d => d.date)
  
  return {
    title: {
      text: props.title,
      textStyle: { color: '#f9fafb', fontSize: 16, fontWeight: 600 },
      left: 'center',
      top: 10
    },
    tooltip: {
      trigger: 'axis',
      backgroundColor: 'rgba(17, 24, 39, 0.95)',
      borderColor: '#374151',
      textStyle: { color: '#f9fafb' },
      formatter: (params: any) => {
        if (!Array.isArray(params)) return ''
        let html = `<div class="text-sm"><b>${(params[0] as { axisValue?: string }).axisValue}</b><br/>`
        params.forEach((p) => {
          const item = p as { seriesName?: string; value?: number; marker?: string }
          if (item.value !== undefined && item.value !== null) {
            html += `${item.marker} ${item.seriesName}: <span class="${item.value >= 0 ? 'text-red-400' : 'text-green-400'}">${item.value.toFixed(4)}${props.unit}</span><br/>`
          }
        })
        return `${html}</div>`
      }
    },
    legend: {
      data: [
        '估算净值',
        ...(props.data.some(d => d.actualValue !== undefined) ? ['实际净值'] : []),
        ...(props.showConfidence ? ['置信区间上界', '置信区间下界'] : [])
      ],
      textStyle: { color: '#9ca3af' },
      top: 35
    },
    grid: {
      left: '3%',
      right: '4%',
      bottom: '10%',
      top: props.title ? '18%' : '12%',
      containLabel: true
    },
    xAxis: {
      type: 'category',
      boundaryGap: false,
      data: dates,
      axisLine: { lineStyle: { color: '#4b5563' } },
      axisLabel: {
        color: '#9ca3af',
        formatter: (value: string) => value.slice(5)
      }
    },
    yAxis: {
      type: 'value',
      scale: true,
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: {
        color: '#9ca3af',
        formatter: `{value}${props.unit}`
      },
      splitLine: { lineStyle: { color: '#1f2937', type: 'dashed' } }
    },
    dataZoom: [
      {
        type: 'inside',
        start: 0,
        end: 100
      },
      {
        type: 'slider',
        start: 0,
        end: 100,
        height: 20,
        bottom: 5,
        borderColor: '#374151',
        fillerColor: 'rgba(59, 130, 246, 0.15)',
        handleStyle: { color: '#3b82f6' },
        textStyle: { color: '#9ca3af' }
      }
    ],
    series: [
      ...(props.showConfidence ? [{
        name: '置信区间',
        type: 'line' as const,
        data: props.data.map(d => [d.upperConfidence, d.lowerConfidence]),
        lineStyle: { opacity: 0 },
        areaStyle: { color: 'rgba(59, 130, 246, 0.1)' },
        symbol: 'none',
        stack: 'confidence'
      }] : []),
      {
        name: '估算净值',
        type: 'line',
        smooth: true,
        symbol: 'circle',
        symbolSize: 6,
        data: props.data.map(d => d.estimatedValue),
        lineStyle: { width: 2.5, color: '#3b82f6' },
        itemStyle: { color: '#3b82f6', borderWidth: 2 },
        areaStyle: {
          color: {
            type: 'linear',
            x: 0, y: 0, x2: 0, y2: 1,
            colorStops: [
              { offset: 0, color: 'rgba(59, 130, 246, 0.25)' },
              { offset: 1, color: 'rgba(59, 130, 246, 0)' }
            ]
          }
        },
        markPoint: {
          data: [
            { type: 'max', name: '最大值', itemStyle: { color: '#ef4444' } },
            { type: 'min', name: '最小值', itemStyle: { color: '#22c55e' } }
          ],
          symbolSize: 50,
          label: { fontSize: 10, color: '#f9fafb' }
        },
        markLine: {
          silent: true,
          data: [{ type: 'average', name: '平均值' }],
          lineStyle: { color: '#f59e0b', type: 'dashed' },
          label: { color: '#f59e0b', fontSize: 10 }
        }
      },
      ...(props.data.some(d => d.actualValue !== undefined) ? [{
        name: '实际净值',
        type: 'line' as const,
        smooth: true,
        symbol: 'diamond',
        symbolSize: 8,
        data: props.data.map(d => d.actualValue ?? null),
        lineStyle: { width: 2, type: 'dashed', color: '#22c55e' },
        itemStyle: { color: '#22c55e' }
      }] : [])
    ],
    backgroundColor: 'transparent'
  } as EChartsOption
})
</script>
