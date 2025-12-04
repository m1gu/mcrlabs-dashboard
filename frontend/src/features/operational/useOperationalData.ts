import * as React from 'react'
import type { OperationalData, OperationalFilters } from './types'
import { fetchOperationalData } from './api'

type OperationalState = {
  data: OperationalData | null
  loading: boolean
  error: string | null
}

const initialState: OperationalState = {
  data: null,
  loading: false,
  error: null,
}

const operationalCache = new Map<string, OperationalData>()

export function useOperationalData(filters: OperationalFilters) {
  const cacheKey = React.useMemo(() => JSON.stringify(filters), [filters])
  const [state, setState] = React.useState<OperationalState>(() => {
    const cached = operationalCache.get(cacheKey)
    if (cached) {
      return { data: cached, loading: false, error: null }
    }
    return initialState
  })

  const refresh = React.useCallback(async () => {
    setState((prev) => ({ ...prev, loading: true, error: null }))
    try {
      const response = await fetchOperationalData(filters)
      operationalCache.set(cacheKey, response)
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
    const cached = operationalCache.get(cacheKey)
    if (cached) {
      setState({ data: cached, loading: false, error: null })
      return
    }
    void refresh()
  }, [cacheKey, refresh])

  return { ...state, refresh }
}
