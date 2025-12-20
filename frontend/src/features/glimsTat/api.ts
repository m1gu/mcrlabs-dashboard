import { parseApiDate } from '../../utils/format'
import { apiFetchV2 } from '../../lib/api'
import type { GlimsTatData } from './types'

interface GlimsTatApiResponse {
  stats: {
    total_samples: number
    average_open_hours: number | null
    percentile_95_open_hours: number | null
    threshold_hours: number | null
  }
  items: Array<{
    sample_id: string
    dispensary_id: number | null
    dispensary_name: string | null
    date_received: string | null
    report_date: string | null
    tests_count: number
    open_time_hours: number
    open_time_label: string
    is_outlier: boolean
  }>
}

export async function fetchGlimsTatSamples(params: {
  dateFrom: string
  dateTo: string
  dispensaryQuery?: string
  minOpenHours: number
  thresholdHours: number
  lookbackDays?: number
  limit?: number
}): Promise<GlimsTatData> {
  const payload = await apiFetchV2<GlimsTatApiResponse>('/glims/tat/slowest', {
    date_from: params.dateFrom,
    date_to: params.dateTo,
    dispensary_query: params.dispensaryQuery || undefined,
    min_open_hours: params.minOpenHours,
    outlier_threshold_hours: params.thresholdHours,
    lookback_days: params.lookbackDays,
    limit: params.limit ?? 50,
  })

  return {
    stats: {
      totalSamples: payload.stats.total_samples,
      averageOpenHours: payload.stats.average_open_hours,
      percentile95OpenHours: payload.stats.percentile_95_open_hours,
      thresholdHours: payload.stats.threshold_hours,
    },
    samples: payload.items.map((item) => ({
      sampleId: item.sample_id,
      dispensaryName: item.dispensary_name,
      dateReceived: parseApiDate(item.date_received),
      reportDate: parseApiDate(item.report_date),
      testsCount: item.tests_count ?? 0,
      openTimeHours: item.open_time_hours ?? 0,
      openTimeLabel: item.open_time_label || '--',
      isOutlier: Boolean(item.is_outlier),
    })),
  }
}
