import { parseISO } from 'date-fns'
import { apiFetch } from '../../lib/api'
import { formatDateLabel } from '../../utils/format'
import type {
  FunnelStage,
  MatrixCycleItem,
  OperationalData,
  OperationalFilters,
  SampleCyclePoint,
  SlowOrderItem,
  ThroughputPoint,
} from './types'

interface OrdersThroughputPointResponse {
  period_start: string
  orders_created: number
  orders_completed: number
  average_completion_hours: number | null
  median_completion_hours: number | null
}

interface OrdersThroughputResponse {
  interval: string
  points: OrdersThroughputPointResponse[]
  totals: {
    orders_created: number
    orders_completed: number
    average_completion_hours: number | null
    median_completion_hours: number | null
  }
}

interface SamplesCyclePointResponse {
  period_start: string
  completed_samples: number
  average_cycle_hours: number | null
  median_cycle_hours: number | null
}

interface SamplesCycleMatrixResponse {
  matrix_type: string
  completed_samples: number
  average_cycle_hours: number | null
}

interface SamplesCycleTimeResponse {
  interval: string
  points: SamplesCyclePointResponse[]
  totals: {
    completed_samples: number
    average_cycle_hours: number | null
    median_cycle_hours: number | null
  }
  by_matrix_type: SamplesCycleMatrixResponse[]
}

interface OrdersFunnelStageResponse {
  stage: string
  count: number
}

interface OrdersFunnelResponse {
  total_orders: number
  stages: OrdersFunnelStageResponse[]
}

interface OrdersSlowestItemResponse {
  order_id: number
  order_reference: string
  customer_name: string | null
  state: string | null
  completion_hours: number | null
  age_hours: number
}

interface OrdersSlowestResponse {
  items: OrdersSlowestItemResponse[]
}

function toTitleCase(value: string | null | undefined): string {
  if (!value) return '--'
  return value
    .toLowerCase()
    .split(/[\s_]+/)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ')
}

export async function fetchOperationalData(filters: OperationalFilters): Promise<OperationalData> {
  const baseParams = {
    date_from: filters.dateFrom,
    date_to: filters.dateTo,
  }

  const [throughput, sampleCycle, funnel, slowest] = await Promise.all([
    apiFetch<OrdersThroughputResponse>('/analytics/orders/throughput', {
      ...baseParams,
      interval: filters.interval,
    }),
    apiFetch<SamplesCycleTimeResponse>('/analytics/samples/cycle-time', {
      ...baseParams,
      interval: filters.interval,
    }),
    apiFetch<OrdersFunnelResponse>('/analytics/orders/funnel', baseParams),
    apiFetch<OrdersSlowestResponse>('/analytics/orders/slowest', {
      ...baseParams,
      limit: 10,
    }),
  ])

  const throughputPoints: ThroughputPoint[] = throughput.points.map((point) => {
    const date = parseISO(point.period_start)
    return {
      date,
      label: formatDateLabel(date),
      ordersCreated: point.orders_created,
      ordersCompleted: point.orders_completed,
      averageCompletionHours: point.average_completion_hours ?? null,
    }
  })

  const sampleCyclePoints: SampleCyclePoint[] = sampleCycle.points.map((point) => {
    const date = parseISO(point.period_start)
    return {
      date,
      label: formatDateLabel(date),
      samplesCompleted: point.completed_samples,
      averageCycleHours: point.average_cycle_hours ?? null,
    }
  })

  const funnelStages: FunnelStage[] =
    funnel.stages?.map((stage) => ({
      label: toTitleCase(stage.stage),
      count: stage.count,
    })) ?? []

  const matrixCycle: MatrixCycleItem[] =
    sampleCycle.by_matrix_type
      ?.map((item) => ({
        matrixType: item.matrix_type || 'Unknown',
        completedSamples: item.completed_samples,
        averageHours: item.average_cycle_hours ?? null,
      }))
      .sort((a, b) => b.completedSamples - a.completedSamples) ?? []

  const slowestOrders: SlowOrderItem[] =
    slowest.items
      ?.slice(0, 10)
      .map((item) => ({
        orderId: item.order_id,
        reference: item.order_reference || `Order ${item.order_id}`,
        customer: item.customer_name || '--',
        state: toTitleCase(item.state),
        completionHours: item.completion_hours ?? null,
        ageHours: item.age_hours,
      })) ?? []

  return {
    kpis: {
      averageLeadTimeHours: throughput.totals.average_completion_hours ?? null,
      medianLeadTimeHours: throughput.totals.median_completion_hours ?? null,
      ordersCompleted: throughput.totals.orders_completed,
      samplesCompleted: sampleCycle.totals.completed_samples,
    },
    throughput: throughputPoints,
    sampleCycle: sampleCyclePoints,
    orderFunnel: funnelStages,
    matrixCycle,
    slowestOrders,
  }
}
