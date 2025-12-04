import { parseISO } from 'date-fns'
import { apiFetch } from '../../lib/api'
import type { SlowReportedOrdersData } from './types'

interface SlowReportedOrdersResponse {
  stats: {
    total_orders: number
    average_open_hours: number | null
    percentile_95_open_hours: number | null
    threshold_hours: number | null
  }
  items: Array<{
    order_id: number
    order_reference: string
    customer_name: string | null
    date_created: string | null
    date_reported: string | null
    samples_count: number | null
    tests_count: number | null
    open_time_hours: number
    open_time_label: string
    is_outlier: boolean
  }>
}

export async function fetchSlowReportedOrders(params: {
  dateFrom: string
  dateTo: string
  customerQuery?: string
  minOpenHours: number
  thresholdHours: number
  lookbackDays?: number
}): Promise<SlowReportedOrdersData> {
  const payload = await apiFetch<SlowReportedOrdersResponse>('/analytics/priority-orders/slowest', {
    date_from: params.dateFrom,
    date_to: params.dateTo,
    customer_query: params.customerQuery || undefined,
    min_open_hours: params.minOpenHours,
    outlier_threshold_hours: params.thresholdHours,
    lookback_days: params.lookbackDays,
    limit: 50,
  })

  return {
    stats: {
      totalOrders: payload.stats.total_orders,
      averageOpenHours: payload.stats.average_open_hours,
      percentile95OpenHours: payload.stats.percentile_95_open_hours,
      thresholdHours: payload.stats.threshold_hours,
    },
    orders: payload.items.map((item) => ({
      id: item.order_id,
      reference: item.order_reference,
      customer: item.customer_name || '--',
      createdAt: item.date_created ? parseISO(item.date_created) : null,
      reportedAt: item.date_reported ? parseISO(item.date_reported) : null,
      samplesCount: item.samples_count ?? 0,
      testsCount: item.tests_count ?? 0,
      openTimeHours: item.open_time_hours ?? 0,
      openTimeLabel: item.open_time_label || '--',
      isOutlier: Boolean(item.is_outlier),
    })),
  }
}
