export type IntervalOption = 'day' | 'week'

export interface PriorityFilters {
  dateFrom: string
  dateTo: string
  interval: IntervalOption
  minDaysOverdue: number
  slaHours: number
}

export interface PriorityKpis {
  totalOverdue: number
  overdueBeyondSla: number
  overdueWithinSla: number
  averageOpenHours: number | null
  maxOpenHours: number | null
  percentOverdueVsActive: number
}

export interface OverdueOrder {
  id: number
  reference: string
  customer: string
  state: string
  createdAt: Date | null
  openHours: number
  slaBreached: boolean
  totalSamples: number
  incompleteSamples: number
  samples: OverdueSample[]
}

export interface OverdueSample {
  id: number
  customId: string
  name: string
  matrixType: string
  totalTests: number
  incompleteTests: number
  tests: OverdueTest[]
}

export interface OverdueTest {
  id: number
  testIds: number[]
  label: string
  states: string[]
}

export interface WarningOrder extends OverdueOrder {}

export interface ReadySample {
  id: number
  customId: string
  name: string
  orderReference: string
  customer: string
  completedAt: Date | null
  testsDone: number
  testsTotal: number
}

export interface MetrcSample {
  id: number
  customId: string
  dateCreated: Date | null
  metrcId: string
  metrcStatus: string
  metrcDate: Date | null
  customer: string
  openTime: string
}

export interface TimelinePoint {
  date: Date
  label: string
  overdueOrders: number
}

export interface HeatmapCustomer {
  customerName: string
  data: Record<string, number>
  total: number
}

export interface HeatmapData {
  periods: string[]
  customers: HeatmapCustomer[]
}

export interface StateBreakdownItem {
  state: string
  count: number
  ratio: number
}

export interface PriorityOrdersData {
  kpis: PriorityKpis
  topOrders: OverdueOrder[]
  warningOrders: WarningOrder[]
  readySamples: ReadySample[]
  metrcSamples: MetrcSample[]
  timeline: TimelinePoint[]
  heatmap: HeatmapData
  stateBreakdown: StateBreakdownItem[]
}
