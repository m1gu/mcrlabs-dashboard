import { parseISO } from 'date-fns'
import { apiFetch } from '../../lib/api'
import { formatDateLabel, parseApiDate } from '../../utils/format'
import type {
  DailyActivityResponse,
  MetricsSummaryResponse,
  NewCustomersResponse,
  OverviewData,
  OverviewFilters,
  ReportsOverviewResponse,
  TestsLabelDistributionResponse,
  TestsTatDailyResponse,
  TopCustomersResponse,
} from './types'

export async function fetchOverviewData(filters: OverviewFilters): Promise<OverviewData> {
  const baseParams = {
    date_from: filters.dateFrom,
    date_to: filters.dateTo,
  }

  const [
    summary,
    reports,
    activity,
    newCustomers,
    topCustomers,
    labelDistribution,
    tatDaily,
  ] = await Promise.all([
    apiFetch<MetricsSummaryResponse>('/metrics/summary', baseParams),
    apiFetch<ReportsOverviewResponse>('/metrics/reports/overview', baseParams),
    apiFetch<DailyActivityResponse>('/metrics/activity/daily', {
      ...baseParams,
      compare_previous: 'false',
    }),
    apiFetch<NewCustomersResponse>('/metrics/customers/new', {
      ...baseParams,
      limit: 10,
    }),
    apiFetch<TopCustomersResponse>('/metrics/customers/top-tests', {
      ...baseParams,
      limit: 10,
    }),
    apiFetch<TestsLabelDistributionResponse>('/metrics/tests/label-distribution', baseParams),
    apiFetch<TestsTatDailyResponse>('/metrics/tests/tat-daily', {
      ...baseParams,
      moving_average_window: filters.timeframe === 'weekly' ? 14 : 7,
    }),
  ])

  const movingAverageMap = new Map<string, number | null>()
  tatDaily.moving_average_hours?.forEach((item) => {
    movingAverageMap.set(item.period_start, item.value ?? null)
  })

  const tatDailySeries =
    tatDaily.points?.map((point) => {
      const date = parseISO(point.date)
      const label = formatDateLabel(date)
      return {
        date,
        label,
        withinSla: point.within_sla,
        beyondSla: point.beyond_sla,
        averageHours: point.average_hours ?? null,
        movingAverageHours: movingAverageMap.get(point.date) ?? null,
      }
    }) ?? []

  return {
    summary: {
      samples: summary.kpis.total_samples,
      tests: summary.kpis.total_tests,
      customers: summary.kpis.total_customers,
      reports: summary.kpis.total_reports,
      avgTatHours: summary.kpis.average_tat_hours,
      lastUpdatedAt: parseApiDate(summary.last_updated_at),
      rangeStart: parseApiDate(summary.range_start),
      rangeEnd: parseApiDate(summary.range_end),
    },
    reports: {
      total: reports.total_reports,
      within: reports.reports_within_sla,
      beyond: reports.reports_beyond_sla,
    },
    dailyActivity:
      activity.current?.map((point) => {
        const date = parseISO(point.date)
        return {
          date,
          label: formatDateLabel(date),
          samples: point.samples,
          tests: point.tests,
          testsReported: point.tests_reported ?? 0,
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
          label: item.label,
          count: item.count,
        }))
        .sort((a, b) => b.count - a.count) ?? [],
    tatDaily: tatDailySeries,
  }
}
