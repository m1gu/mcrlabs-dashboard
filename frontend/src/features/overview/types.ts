export type TimeframeOption = 'daily' | 'weekly'

export interface OverviewFilters {
  dateFrom: string
  dateTo: string
  timeframe: TimeframeOption
  sampleType?: string
}

export interface MetricsSummaryResponse {
  kpis: {
    total_samples: number
    total_tests: number
    total_customers: number
    total_reports: number
    average_tat_hours: number | null
  }
  last_updated_at: string | null
  range_start: string | null
  range_end: string | null
}

export interface ReportsOverviewResponse {
  total_reports: number
  reports_within_sla: number
  reports_beyond_sla: number
}

export interface DailyActivityResponse {
  current: Array<{
    date: string
    samples: number
    tests: number
    tests_reported: number
  }>
  previous?: Array<{
    date: string
    samples: number
    tests: number
    tests_reported: number
  }>
}

export interface NewCustomersResponse {
  customers: Array<{
    id: number
    name: string
    created_at: string
  }>
}

export interface TopCustomersResponse {
  customers: Array<{
    id: number
    name: string
    tests: number
    tests_reported: number
  }>
}

export interface TestsLabelDistributionResponse {
  labels: Array<{
    label: string
    count: number
  }>
}

export interface TestsTatDailyResponse {
  points: Array<{
    date: string
    average_hours: number | null
    within_sla: number
    beyond_sla: number
  }>
  moving_average_hours?: Array<{
    period_start: string
    value: number | null
  }>
}

export interface OverviewData {
  summary: {
    samples: number
    tests: number
    customers: number
    reports: number
    avgTatHours: number | null
    samplesByType?: Record<string, number>
    testsByType?: Record<string, number>
    reportsByType?: Record<string, number>
    tatByType?: Record<string, number>
    lastUpdatedAt: Date | null
    rangeStart: Date | null
    rangeEnd: Date | null
  }
  reports: {
    total: number
    within: number
    beyond: number
  }
  dailyActivity: Array<{
    date: Date
    label: string
    samples: number
    tests: number
    testsReported: number
    samplesBreakdown?: Record<string, number>
    testsBreakdown?: Record<string, number>
    reportedBreakdown?: Record<string, number>
  }>
  newCustomers: Array<{
    id: number
    name: string
    createdAt: Date
  }>
  topCustomers: Array<{
    id: number
    name: string
    tests: number
    testsReported: number
  }>
  testsByLabel: Array<{
    label: string
    count: number
    breakdown?: Record<string, number>
  }>
  tatDaily: Array<{
    date: Date
    label: string
    withinSla: number
    beyondSla: number
    averageHours: number | null
    movingAverageHours: number | null
  }>
}
