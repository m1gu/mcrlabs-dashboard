export type IntervalOption = 'day' | 'week'

export interface OperationalFilters {
  dateFrom: string
  dateTo: string
  interval: IntervalOption
}

export interface ThroughputPoint {
  date: Date
  label: string
  ordersCreated: number
  ordersCompleted: number
  averageCompletionHours: number | null
}

export interface SampleCyclePoint {
  date: Date
  label: string
  samplesCompleted: number
  averageCycleHours: number | null
}

export interface FunnelStage {
  label: string
  count: number
}

export interface MatrixCycleItem {
  matrixType: string
  completedSamples: number
  averageHours: number | null
}

export interface SlowOrderItem {
  orderId: number
  reference: string
  customer: string
  state: string
  completionHours: number | null
  ageHours: number
}

export interface OperationalData {
  kpis: {
    averageLeadTimeHours: number | null
    medianLeadTimeHours: number | null
    ordersCompleted: number
    samplesCompleted: number
  }
  throughput: ThroughputPoint[]
  sampleCycle: SampleCyclePoint[]
  orderFunnel: FunnelStage[]
  matrixCycle: MatrixCycleItem[]
  slowestOrders: SlowOrderItem[]
}
