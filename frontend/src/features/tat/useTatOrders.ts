import * as React from 'react'
import type { TatFilters, SlowReportedOrdersData } from './types'
import { fetchSlowReportedOrders } from './api'

type TatState = {
  data: SlowReportedOrdersData | null
  loading: boolean
  error: string | null
}

const initialState: TatState = { data: null, loading: false, error: null }
const tatCache = new Map<string, SlowReportedOrdersData>()

export function useTatOrders(filters: TatFilters, options: { lookbackDays?: number }) {
  const cacheKey = React.useMemo(() => JSON.stringify({ ...filters, lookbackDays: options.lookbackDays }), [filters, options.lookbackDays])
  const [state, setState] = React.useState<TatState>(() => {
    const cached = tatCache.get(cacheKey)
    if (cached) {
      return { data: cached, loading: false, error: null }
    }
    return initialState
  })

  const refresh = React.useCallback(async () => {
    setState((prev) => ({ ...prev, loading: true, error: null }))
    try {
      const response = await fetchSlowReportedOrders({
        dateFrom: filters.dateFrom,
        dateTo: filters.dateTo,
        customerQuery: filters.customerQuery,
        minOpenHours: filters.minOpenHours,
        thresholdHours: filters.thresholdHours,
        lookbackDays: options.lookbackDays,
      })
      tatCache.set(cacheKey, response)
      setState({ data: response, loading: false, error: null })
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Unknown error'
      setState((prev) => ({ data: prev.data, loading: false, error: message }))
    }
  }, [filters, options.lookbackDays])

  React.useEffect(() => {
    const cached = tatCache.get(cacheKey)
    if (cached) {
      setState({ data: cached, loading: false, error: null })
      return
    }
    void refresh()
  }, [cacheKey, refresh])

  return { ...state, refresh }
}
