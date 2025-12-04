export interface SlowReportedOrdersStats {
  totalOrders: number
  averageOpenHours: number | null
  percentile95OpenHours: number | null
  thresholdHours: number | null
}

export interface SlowReportedOrder {
  id: number
  reference: string
  customer: string
  createdAt: Date | null
  reportedAt: Date | null
  samplesCount: number
  testsCount: number
  openTimeHours: number
  openTimeLabel: string
  isOutlier: boolean
}

export interface SlowReportedOrdersData {
  stats: SlowReportedOrdersStats
  orders: SlowReportedOrder[]
}

export interface TatFilters {
  dateFrom: string
  dateTo: string
  customerQuery: string
  minOpenHours: number
  thresholdHours: number
}
