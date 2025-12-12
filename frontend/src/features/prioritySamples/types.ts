export interface PrioritySamplesFilters {
  minDaysOverdue: number
  tatHours: number
}

export interface PriorityTest {
  label: string
  startDate: string | null
  complete: boolean
}

export interface PrioritySample {
  sampleId: string
  clientName: string | null
  dispensaryName: string | null
  dateReceived: string | null
  reportDate: string | null
  openHours: number | null
  testsTotal: number
  testsComplete: number
  tests: PriorityTest[]
}

export interface PrioritySamplesData {
  samples: PrioritySample[]
  heatmap: HeatmapData
  metrcSamples: MetrcSample[]
}

export interface HeatmapData {
  periods: string[]
  customers: HeatmapCustomer[]
}

export interface HeatmapCustomer {
  customerName: string
  data: Record<string, number>
  total: number
}

export interface MetrcSample {
  id: number
  customId: string
  dateCreated: string | null
  metrcId: string
  metrcStatus: string
  metrcDate: string | null
  customer: string
  openTime: string
}
