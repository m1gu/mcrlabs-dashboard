import { parseISO } from 'date-fns'
import { apiFetch } from '../../lib/api'
import { formatDateLabel, formatElapsedDaysHours } from '../../utils/format'
import type {
  HeatmapCustomer,
  HeatmapData,
  OverdueOrder,
  PriorityFilters,
  PriorityOrdersData,
  PriorityKpis,
  ReadySample,
  StateBreakdownItem,
  TimelinePoint,
  WarningOrder,
  MetrcSample,
} from './types'

interface OverdueOrdersResponse {
  interval: string
  minimum_days_overdue: number
  warning_window_days: number
  sla_hours: number
  kpis: {
    total_overdue: number
    average_open_hours: number | null
    max_open_hours: number | null
    percent_overdue_vs_active: number
    overdue_beyond_sla: number
    overdue_within_sla: number
  }
  top_orders: Array<{
    order_id: number
    custom_formatted_id: string | null
    customer_name: string | null
    state: string | null
    date_created: string | null
    open_hours: number
    total_samples: number
    incomplete_sample_count: number
    incomplete_samples: Array<{
      sample_id: number
      sample_custom_id: string | null
      sample_name: string | null
      matrix_type: string | null
      total_tests: number
      incomplete_tests: number
      tests: Array<{
        primary_test_id: number
        test_ids: number[]
        label_abbr: string | null
        states: string[] | null
      }>
    }>
  }>
  warning_orders: Array<{
    order_id: number
    custom_formatted_id: string | null
    customer_name: string | null
    state: string | null
    date_created: string | null
    open_hours: number
    total_samples: number
    incomplete_sample_count: number
    incomplete_samples: Array<{
      sample_id: number
      sample_custom_id: string | null
      sample_name: string | null
      matrix_type: string | null
      total_tests: number
      incomplete_tests: number
      tests: Array<{
        primary_test_id: number
        test_ids: number[]
        label_abbr: string | null
        states: string[] | null
      }>
    }>
  }>
  ready_to_report_samples: Array<{
    sample_id: number
    sample_custom_id: string | null
    sample_name: string | null
    order_custom_id: string | null
    customer_name: string | null
    completed_date: string | null
    tests_ready_count: number
    tests_total_count: number
  }>
  timeline: Array<{
    period_start: string
    overdue_orders: number
  }>
  heatmap: Array<{
    customer_name: string | null
    period_start: string
    overdue_orders: number
  }>
  state_breakdown: Array<{
    state: string | null
    count: number
    ratio: number
  }>
  metrc_samples: Array<{
    sample_id: number
    sample_custom_id: string | null
    date_created: string | null
    metrc_id: string
    metrc_status: string | null
    metrc_date: string | null
    customer_name: string | null
  }>
}

const DEFAULT_WARNING_WINDOW = 5

function toTitleCase(value: string | null | undefined): string {
  if (!value) return '--'
  return value
    .toLowerCase()
    .split(/[\s_]+/)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ')
}

function buildKpis(response: OverdueOrdersResponse): PriorityKpis {
  const kpis = response.kpis
  return {
    totalOverdue: kpis.total_overdue,
    overdueBeyondSla: kpis.overdue_beyond_sla,
    overdueWithinSla: kpis.overdue_within_sla,
    averageOpenHours: kpis.average_open_hours,
    maxOpenHours: kpis.max_open_hours,
    percentOverdueVsActive: kpis.percent_overdue_vs_active,
  }
}

function mapOrders(entries: OverdueOrdersResponse['top_orders'], slaHours: number): OverdueOrder[] {
  const threshold = Number.isFinite(slaHours) ? slaHours : Number.POSITIVE_INFINITY
  return entries.map((item) => ({
    id: item.order_id,
    reference: item.custom_formatted_id || `Order ${item.order_id}`,
    customer: item.customer_name || '--',
    state: toTitleCase(item.state),
    createdAt: item.date_created ? parseISO(item.date_created) : null,
    openHours: item.open_hours,
    slaBreached: item.open_hours > threshold,
    totalSamples: item.total_samples ?? 0,
    incompleteSamples: item.incomplete_sample_count ?? (item.incomplete_samples?.length ?? 0),
    samples:
      item.incomplete_samples?.map((sample) => ({
        id: sample.sample_id,
        customId: sample.sample_custom_id || '--',
        name: sample.sample_name || '--',
        matrixType: sample.matrix_type || '--',
        totalTests: sample.total_tests ?? 0,
        incompleteTests: sample.incomplete_tests ?? 0,
        tests:
          sample.tests?.map((test) => {
            const states = test.states
              ? test.states.map((state) => toTitleCase(state))
              : []
            const testIds =
              Array.isArray(test.test_ids) && test.test_ids.length
                ? test.test_ids
                : [test.primary_test_id]
            return {
              id: test.primary_test_id,
              testIds,
              label: test.label_abbr || '--',
              states,
            }
          }) ?? [],
      })) ?? [],
  }))
}

function mapWarnings(entries: OverdueOrdersResponse['warning_orders'], slaHours: number): WarningOrder[] {
  return mapOrders(entries, slaHours)
}

function mapReadySamples(entries: OverdueOrdersResponse['ready_to_report_samples']): ReadySample[] {
  return entries.map((item) => ({
    id: item.sample_id,
    customId: item.sample_custom_id || item.sample_name || `Sample ${item.sample_id}`,
    name: item.sample_name || `Sample ${item.sample_id}`,
    orderReference: item.order_custom_id || '--',
    customer: item.customer_name || '--',
    completedAt: item.completed_date ? parseISO(item.completed_date) : null,
    testsDone: item.tests_ready_count,
    testsTotal: item.tests_total_count,
  }))
}

function mapMetrcSamples(entries: OverdueOrdersResponse['metrc_samples']): MetrcSample[] {
  return entries.map((item) => {
    const dateCreated = item.date_created ? parseISO(item.date_created) : null
    const metrcDate = item.metrc_date ? parseISO(item.metrc_date) : null
    return {
      id: item.sample_id,
      customId: item.sample_custom_id || `Sample ${item.sample_id}`,
      dateCreated,
      metrcId: item.metrc_id,
      metrcStatus: item.metrc_status || '--',
      metrcDate,
      customer: item.customer_name || '--',
      openTime: formatElapsedDaysHours(metrcDate),
    }
  })
}

function mapTimeline(entries: OverdueOrdersResponse['timeline']): TimelinePoint[] {
  return entries.map((point) => {
    const date = parseISO(point.period_start)
    return {
      date,
      label: formatDateLabel(date),
      overdueOrders: point.overdue_orders,
    }
  })
}

function mapHeatmap(entries: OverdueOrdersResponse['heatmap']): HeatmapData {
  if (!entries.length) {
    return { periods: [], customers: [] }
  }

  const periods = Array.from(
    new Set(
      entries
        .map((item) => item.period_start)
        .filter((value): value is string => Boolean(value)),
    ),
  ).sort()

  const customersMap = new Map<string, HeatmapCustomer>()

  for (const item of entries) {
    const customerName = item.customer_name || 'Unknown'
    const key = customerName

    if (!customersMap.has(key)) {
      customersMap.set(key, {
        customerName,
        data: {},
        total: 0,
      })
    }

    const customer = customersMap.get(key)!
    customer.data[item.period_start] = item.overdue_orders
    customer.total += item.overdue_orders
  }

  const customers = Array.from(customersMap.values()).sort((a, b) => b.total - a.total)

  return {
    periods,
    customers,
  }
}

function mapStateBreakdown(entries: OverdueOrdersResponse['state_breakdown']): StateBreakdownItem[] {
  return entries.map((item) => ({
    state: toTitleCase(item.state),
    count: item.count,
    ratio: item.ratio,
  }))
}

export async function fetchPriorityOrders(filters: PriorityFilters): Promise<PriorityOrdersData> {
  const overdueResponse = await apiFetch<OverdueOrdersResponse>('/analytics/orders/overdue', {
    date_from: filters.dateFrom,
    date_to: filters.dateTo,
    interval: filters.interval,
    min_days_overdue: filters.minDaysOverdue,
    warning_window_days: DEFAULT_WARNING_WINDOW,
    sla_hours: filters.slaHours,
    top_limit: 20,
    client_limit: 20,
    warning_limit: 10,
  })

  return {
    kpis: buildKpis(overdueResponse),
    topOrders: mapOrders(overdueResponse.top_orders, overdueResponse.sla_hours),
    warningOrders: mapWarnings(overdueResponse.warning_orders, overdueResponse.sla_hours),
    readySamples: mapReadySamples(overdueResponse.ready_to_report_samples),
    metrcSamples: mapMetrcSamples(overdueResponse.metrc_samples),
    timeline: mapTimeline(overdueResponse.timeline),
    heatmap: mapHeatmap(overdueResponse.heatmap),
    stateBreakdown: mapStateBreakdown(overdueResponse.state_breakdown),
  }
}
