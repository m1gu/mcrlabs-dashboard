import { subDays } from 'date-fns'
import { apiFetch, apiFetchV2 } from '../../lib/api'
import { formatApiDateTimeUtc, formatElapsedDaysHours, parseApiDate } from '../../utils/format'
import type {
  HeatmapCustomer,
  HeatmapData,
  MetrcSample,
  PrioritySample,
  PrioritySamplesData,
  PrioritySamplesFilters,
} from './types'

interface MostOverdueResponse {
  samples: Array<{
    sample_id: string
    client_name: string | null
    dispensary_id: number | null
    dispensary_name: string | null
    date_received: string | null
    report_date: string | null
    open_hours: number | null
    tests_total: number
    tests_complete: number
    tests: Array<{
      label: string
      start_date: string | null
      complete: boolean
      status?: string | null
    }>
    status?: string | null
  }>
}

interface HeatmapResponse {
  buckets: Array<{
    dispensary_id: number | null
    dispensary_name: string | null
    period_start: string
    count: number
  }>
}

// Reuse v1 priority endpoint only for METRC samples
interface OverdueOrdersResponse {
  metrc_samples: Array<{
    sample_id: number
    sample_custom_id: string | null
    date_created: string | null
    metrc_id: string
    metrc_status: string | null
    metrc_date: string | null
    open_time_label: string | null
    customer_name: string | null
  }>
}

function mapSamples(resp: MostOverdueResponse): PrioritySample[] {
  return resp.samples.map((s) => ({
    sampleId: s.sample_id,
    clientName: s.client_name,
    dispensaryName: s.dispensary_name,
    dateReceived: s.date_received,
    reportDate: s.report_date,
    openHours: s.open_hours,
    testsTotal: s.tests_total,
    testsComplete: s.tests_complete,
    tests: s.tests.map((t) => ({
      label: t.label,
      startDate: t.start_date,
      complete: t.complete,
      status: t.status ?? null,
    })),
    status: s.status ?? null,
  }))
}

function mapHeatmap(resp: HeatmapResponse): HeatmapData {
  if (!resp.buckets.length) return { periods: [], customers: [] }
  const periods = Array.from(new Set(resp.buckets.map((b) => b.period_start))).sort()
  const byCustomer = new Map<string, HeatmapCustomer>()
  for (const b of resp.buckets) {
    const name = b.dispensary_name || 'Unknown'
    if (!byCustomer.has(name)) {
      byCustomer.set(name, { customerName: name, data: {}, total: 0 })
    }
    const entry = byCustomer.get(name)!
    entry.data[b.period_start] = b.count
    entry.total += b.count
  }
  const customers = Array.from(byCustomer.values()).sort((a, b) => b.total - a.total)
  return { periods, customers }
}

function mapMetrcSamples(resp: OverdueOrdersResponse): MetrcSample[] {
  return resp.metrc_samples.map((item) => ({
    id: item.sample_id,
    customId: item.sample_custom_id || `Sample ${item.sample_id}`,
    dateCreated: item.date_created,
    metrcId: item.metrc_id,
    metrcStatus: item.metrc_status || '--',
    metrcDate: item.metrc_date,
    customer: item.customer_name || '--',
    // Use the backend provided label if available, fallback to calc
    openTime: item.open_time_label || formatElapsedDaysHours(parseApiDate(item.metrc_date)),
  }))
}

export async function fetchPrioritySamples(filters: PrioritySamplesFilters): Promise<PrioritySamplesData> {
  const overdue = await apiFetchV2<MostOverdueResponse>('/glims/priority/most-overdue', {
    min_days_overdue: filters.minDaysOverdue,
  })
  const heatmap = await apiFetchV2<HeatmapResponse>('/glims/priority/overdue-heatmap', {
    min_days_overdue: filters.minDaysOverdue,
    bucket: 'week',
  })
  // reuse v1 for METRC samples
  const now = new Date()
  const start = subDays(now, 30)
  let metrcSamples: MetrcSample[] = []
  try {
    const metrcResp = await apiFetch<OverdueOrdersResponse>('/analytics/orders/overdue', {
      date_from: formatApiDateTimeUtc(start),
      date_to: formatApiDateTimeUtc(now),
      interval: 'day',
      min_days_overdue: 0,
      warning_window_days: 0,
      sla_hours: 0,
      top_limit: 1,
      client_limit: 1,
      warning_limit: 1, // must be >=1 per API schema
      metrc_limit: 30,
    })
    metrcSamples = mapMetrcSamples(metrcResp)
  } catch {
    metrcSamples = []
  }

  return {
    samples: mapSamples(overdue),
    heatmap: mapHeatmap(heatmap),
    metrcSamples,
  }
}
