// FUND-OS 图表组件统一导出
export { default as BaseChart } from './BaseChart.vue'
export { default as FundKLineChart } from './FundKLineChart.vue'
export { default as FundEstimateChart } from './FundEstimateChart.vue'
export { default as PortfolioPieChart } from './PortfolioPieChart.vue'
export { default as FundHeatmap } from './FundHeatmap.vue'
export { default as RealTimeQuoteChart } from './RealTimeQuoteChart.vue'

// 图表类型定义
export interface KLineData {
  date: string
  open: number
  high: number
  low: number
  close: number
  volume?: number
}

export interface EstimationPoint {
  date: string
  estimatedValue: number
  actualValue?: number
  upperConfidence?: number
  lowerConfidence?: number
}

export interface PortfolioItem {
  name: string
  value: number
  percentage?: number
  color?: string
  category?: string
}

export interface QuotePoint {
  time: string
  price: number
  volume?: number
  avgPrice?: number
}
