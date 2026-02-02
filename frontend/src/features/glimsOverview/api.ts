import { apiFetchV2 } from '../../lib/api'
import { formatDateLabel, parseApiDate } from '../../utils/format'
import type { OverviewData } from '../overview/types'
import type {
  GlimsActivityResponse,
  GlimsNewCustomersFromSheetResponse,
  GlimsOverviewFilters,
  GlimsSummaryResponse,
  GlimsTatDailyResponse,
  GlimsTestsByLabelResponse,
  GlimsTopCustomersResponse,
} from './types'

export async function fetchGlimsOverviewData(filters: GlimsOverviewFilters): Promise<OverviewData> {
  const baseParams: Record<string, any> = {
    date_from: filters.dateFrom,
    date_to: filters.dateTo,
  }

  if (filters.customerId) {
    baseParams.dispensary_id = filters.customerId
  }

  const [summary, activity, newCustomers, topCustomers, labelDistribution, tatDaily] = await Promise.all([
    apiFetchV2<GlimsSummaryResponse>('/glims/overview/summary', { ...baseParams, sample_type: filters.sampleType, timeframe: filters.timeframe }),
    apiFetchV2<GlimsActivityResponse>('/glims/overview/activity', { ...baseParams, sample_type: filters.sampleType, timeframe: filters.timeframe }),
    apiFetchV2<GlimsNewCustomersFromSheetResponse>('/glims/overview/customers/new-from-sheet', {
      ...baseParams,
      limit: 10,
    }),
    apiFetchV2<GlimsTopCustomersResponse>('/glims/overview/customers/top-tests', {
      ...baseParams,
      limit: 10,
    }),
    apiFetchV2<GlimsTestsByLabelResponse>('/glims/overview/tests/by-label', { ...baseParams, sample_type: filters.sampleType, timeframe: filters.timeframe }),
    apiFetchV2<GlimsTatDailyResponse>('/glims/overview/tat-daily', {
      ...baseParams,
      sample_type: filters.sampleType,
      timeframe: filters.timeframe,
      tat_target_hours: 72,
      moving_average_window: filters.timeframe === 'weekly' ? 14 : filters.timeframe === 'monthly' ? 3 : 7,
    }),
  ])

  const tatDailySeries =
    tatDaily.points?.map((point) => {
      const date = parseApiDate(point.date)!
      return {
        date,
        label: formatDateLabel(date),
        withinSla: point.within_tat,
        beyondSla: point.beyond_tat,
        averageHours: point.average_hours ?? null,
        movingAverageHours: point.moving_average_hours ?? null,
        withinBreakdown: point.within_breakdown,
        beyondBreakdown: point.beyond_breakdown,
        hours_breakdown: point.hours_breakdown,
      }
    }) ?? []

  return {
    summary: {
      samples: summary.samples,
      tests: summary.tests,
      customers: summary.customers,
      reports: summary.reports,
      avgTatHours: summary.avg_tat_hours,
      samplesByType: summary.samples_by_type,
      testsByType: summary.tests_by_type,
      reportsByType: summary.reports_by_type,
      tatByType: summary.tat_by_type,
      lastUpdatedAt: summary.last_updated_at ? parseApiDate(summary.last_updated_at) : null,
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
        const date = parseApiDate(point.date)!
        return {
          date,
          label: formatDateLabel(date),
          samples: point.samples,
          tests: point.tests,
          testsReported: point.samples_reported,
          samplesBreakdown: point.samples_breakdown,
          testsBreakdown: point.tests_breakdown,
          reportedBreakdown: point.reported_breakdown,
        }
      }) ?? [],
    newCustomers:
      newCustomers.customers?.map((customer) => ({
        id: customer.client_id,
        name: customer.client_name,
        createdAt: parseApiDate(customer.date_created)!,
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
          breakdown: item.breakdown,
        }))
        .sort((a, b) => b.count - a.count) ?? [],
    tatDaily: tatDailySeries,
  }
}

export async function fetchGlimsCustomersList(
  dateFrom: string,
  dateTo: string
): Promise<any> {
  return apiFetchV2('/glims/overview/customers/list', {
    date_from: dateFrom,
    date_to: dateTo,
  })
}
