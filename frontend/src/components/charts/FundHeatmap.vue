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

interface HeatmapCell {
  date: string
  fundCode: string
  fundName: string
  value: number // 收益率，正负表示涨跌
}

interface Props {
  data: HeatmapCell[]
  fundCodes?: string[]
  height?: string
  loading?: boolean
  title?: string
}

const props = withDefaults(defineProps<Props>(), {
  height: '500px',
  loading: false,
  title: '基金收益热力图'
})

// 获取所有唯一基金代码和日期
const uniqueFunds = computed(() => {
  if (props.fundCodes?.length) return props.fundCodes
  const funds = [...new Set(props.data.map(d => d.fundCode))]
  return funds.sort()
})

const uniqueDates = computed(() => {
  return [...new Set(props.data.map(d => d.date))].sort()
})

// 构建热力图数据矩阵
function buildHeatmapData(): [number, number, number][] {
  const result: [number, number, number][] = []
  
  props.data.forEach(cell => {
    const xIndex = uniqueDates.value.indexOf(cell.date)
    const yIndex = uniqueFunds.value.indexOf(cell.fundCode)
    
    if (xIndex !== -1 && yIndex !== -1) {
      result.push([xIndex, yIndex, cell.value])
    }
  })
  
  return result
}

// 根据收益率获取颜色
function getHeatColor(value: number): string {
  if (value > 3) return '#ef4444'   // 深红
  if (value > 2) return '#f87171'   // 红
  if (value > 1) return '#fca5a5'   // 浅红
  if (value > 0) return '#fecaca'   // 很浅红
  if (value === 0) return '#374151' // 灰色（平盘）
  if (value > -1) return '#bbf7d0'  // 很浅绿
  if (value > -2) return '#86efac'  // 浅绿
  if (value > -3) return '#4ade80'  // 绿
  return '#16a34a'                  // 深绿
}

const chartOption = computed(() => {
  return {
    title: {
      text: props.title,
      left: 'center',
      textStyle: { color: '#f9fafb', fontSize: 16 }
    },
    tooltip: {
      position: 'top',
      backgroundColor: 'rgba(17, 24, 39, 0.95)',
      borderColor: '#374151',
      textStyle: { color: '#f9fafb' },
      formatter: (params: any) => {
        if (!Array.isArray(params) || !params.length) return ''
        const p = params[0] as {
          data?: number[];
          value?: number;
          dataIndex?: number
        }
        if (!p.data) return ''
        
        const dateIdx = p.data[0]
        const fundIdx = p.data[1]
        const value = p.data[2]
        
        return `
          <div class="text-sm">
            <div class="font-bold">${uniqueFunds.value[fundIdx]}</div>
            <div>日期: ${uniqueDates.value[dateIdx]}</div>
            <div class="${value >= 0 ? 'text-red-400' : 'text-green-400'}">
              收益率: ${value >= 0 ? '+' : ''}${value.toFixed(2)}%
            </div>
          </div>
        `.trim()
      }
    },
    grid: {
      left: '15%',
      right: '10%',
      top: '12%',
      bottom: '15%',
      containLabel: true
    },
    xAxis: {
      type: 'category',
      data: uniqueDates.value,
      splitArea: { show: true, areaStyle: { color: ['rgba(31, 41, 55, 0.5)', 'rgba(17, 24, 39, 0.3)'] } },
      axisLabel: {
        color: '#9ca3af',
        fontSize: 11,
        formatter: (v: string) => v.slice(5).replace('-', '/')
      },
      axisLine: { lineStyle: { color: '#4b5563' } }
    },
    yAxis: {
      type: 'category',
      data: uniqueFunds.value,
      splitArea: { show: true, areaStyle: { color: ['rgba(31, 41, 55, 0.5)', 'rgba(17, 24, 39, 0.3)'] } },
      axisLabel: {
        color: '#9ca3af',
        fontSize: 11,
        width: 100,
        overflow: 'truncate'
      },
      axisLine: { lineStyle: { color: '#4b5563' } }
    },
    visualMap: {
      min: -5,
      max: 5,
      calculable: true,
      orient: 'horizontal',
      left: 'center',
      bottom: 0,
      inRange: {
        color: ['#22c55e', '#86efac', '#374151', '#fca5a5', '#ef4444']
      },
      textStyle: { color: '#9ca3af' },
      formatter: '{value}%'
    },
    series: [{
      type: 'heatmap',
      data: buildHeatmapData(),
      label: {
        show: true,
        formatter: (params: any) => {
          const v = (params as { value?: number }).value
          if (v === undefined) return ''
          return `${v >= 0 ? '+' : ''}${v.toFixed(1)}`
        },
        fontSize: 10,
        color: '#fff'
      },
      emphasis: {
        itemStyle: {
          shadowBlur: 10,
          shadowColor: 'rgba(0, 0, 0, 0.5)'
        }
      },
      itemStyle: {
        borderColor: '#1f2937',
        borderWidth: 2,
        borderRadius: 4
      },
      progressive: 200,
      animation: true
    }],
    backgroundColor: 'transparent'
  } as EChartsOption
})
</script>
