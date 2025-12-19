import { parseISO } from 'date-fns'
import { apiFetchV2 } from '../../lib/api'
import { formatDateLabel, parseApiDate } from '../../utils/format'
import type { OverviewData } from '../overview/types'
import type {
  GlimsActivityResponse,
  GlimsNewCustomersResponse,
  GlimsOverviewFilters,
  GlimsSummaryResponse,
  GlimsTatDailyResponse,
  GlimsTestsByLabelResponse,
  GlimsTopCustomersResponse,
} from './types'

export async function fetchGlimsOverviewData(filters: GlimsOverviewFilters): Promise<OverviewData> {
  const baseParams = {
    date_from: filters.dateFrom,
    date_to: filters.dateTo,
  }

  const [summary, activity, newCustomers, topCustomers, labelDistribution, tatDaily] = await Promise.all([
    apiFetchV2<GlimsSummaryResponse>('/glims/overview/summary', baseParams),
    apiFetchV2<GlimsActivityResponse>('/glims/overview/activity', baseParams),
    apiFetchV2<GlimsNewCustomersResponse>('/glims/overview/customers/new', {
      ...baseParams,
      limit: 10,
    }),
    apiFetchV2<GlimsTopCustomersResponse>('/glims/overview/customers/top-tests', {
      ...baseParams,
      limit: 10,
    }),
    apiFetchV2<GlimsTestsByLabelResponse>('/glims/overview/tests/by-label', baseParams),
    apiFetchV2<GlimsTatDailyResponse>('/glims/overview/tat-daily', {
      ...baseParams,
      tat_target_hours: 72,
      moving_average_window: filters.timeframe === 'weekly' ? 14 : 7,
    }),
  ])

  const tatDailySeries =
    tatDaily.points?.map((point) => {
      const date = parseISO(point.date)
      return {
        date,
        label: formatDateLabel(date),
        withinSla: point.within_tat,
        beyondSla: point.beyond_tat,
        averageHours: point.average_hours ?? null,
        movingAverageHours: point.moving_average_hours ?? null,
      }
    }) ?? []

  return {
    summary: {
      samples: summary.samples,
      tests: summary.tests,
      customers: summary.customers,
      reports: summary.reports,
      avgTatHours: summary.avg_tat_hours,
      lastUpdatedAt: summary.last_updated_at ? parseISO(summary.last_updated_at) : null,
      rangeStart: parseApiDate(filters.dateFrom),
      rangeEnd: parseApiDate(filters.dateTo),
    },
    reports: {
      total: summary.reports,
      within: 0,
      beyond: 0,
    },
    dailyActivity:
      activity.points?.map((point) => {
        const date = parseISO(point.date)
        const breakdown = point.samples_breakdown || {}
        const flattenedBreakdown: Record<string, number> = {}
        Object.entries(breakdown).forEach(([key, count]) => {
          // Normalize key to be safe for recharts (remove spaces/special chars if needed)
          // For now we keep it simple or just use the key directly if it's clean enough
          // We'll prefix to avoid collisions
          flattenedBreakdown[`samples_${key}`] = count
        })

        return {
          date,
          label: formatDateLabel(date),
          samples: point.samples,
          tests: point.tests,
          testsReported: point.samples_reported,
          ...flattenedBreakdown,
        }
      }) ?? [],
    newCustomers:
      newCustomers.customers?.map((customer) => ({
        id: customer.id,
        name: customer.name,
        createdAt: parseISO(customer.created_at),
      })) ?? [],
    topCustomers:
      topCustomers.customers
        ?.map((customer) => ({
          id: customer.id,
          name: customer.name,
          tests: customer.tests,
          testsReported: customer.tests_reported ?? 0,
        }))
        .sort((a, b) => b.tests - a.tests) ?? [],
    testsByLabel:
      labelDistribution.labels
        ?.map((item) => ({
          label: item.key,
          count: item.count,
        }))
        .sort((a, b) => b.count - a.count) ?? [],
    tatDaily: tatDailySeries,
  }
}
