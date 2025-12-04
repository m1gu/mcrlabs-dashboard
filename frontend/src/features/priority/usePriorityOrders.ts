import * as React from 'react'
import type { PriorityFilters, PriorityOrdersData } from './types'
import { fetchPriorityOrders } from './api'

type PriorityState = {
  data: PriorityOrdersData | null
  loading: boolean
  error: string | null
}

const initialState: PriorityState = {
  data: null,
  loading: false,
  error: null,
}

const priorityCache = new Map<string, PriorityOrdersData>()

export function usePriorityOrders(filters: PriorityFilters) {
  const cacheKey = React.useMemo(() => JSON.stringify(filters), [filters])
  const [state, setState] = React.useState<PriorityState>(() => {
    const cached = priorityCache.get(cacheKey)
    if (cached) {
      return { data: cached, loading: false, error: null }
    }
    return initialState
  })

  const refresh = React.useCallback(async () => {
    setState((prev) => ({ ...prev, loading: true, error: null }))
    try {
      const response = await fetchPriorityOrders(filters)
      priorityCache.set(cacheKey, response)
      setState({
        data: response,
        loading: false,
        error: null,
      })
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Unknown error'
      setState((prev) => ({
        data: prev.data,
        loading: false,
        error: message,
      }))
    }
  }, [cacheKey, filters])

  React.useEffect(() => {
    const cached = priorityCache.get(cacheKey)
    if (cached) {
      setState({ data: cached, loading: false, error: null })
      return
    }
    void refresh()
  }, [cacheKey, refresh])

  return { ...state, refresh }
}
