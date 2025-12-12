import * as React from 'react'
import type { OverviewData } from '../overview/types'
import type { GlimsOverviewFilters } from './types'
import { fetchGlimsOverviewData } from './api'

type UseOverviewDataState = {
  data: OverviewData | null
  loading: boolean
  error: string | null
}

const initialState: UseOverviewDataState = {
  data: null,
  loading: false,
  error: null,
}

const overviewCache = new Map<string, OverviewData>()

export function useGlimsOverviewData(filters: GlimsOverviewFilters) {
  const cacheKey = React.useMemo(() => JSON.stringify(filters), [filters])
  const [state, setState] = React.useState<UseOverviewDataState>(() => {
    const cached = overviewCache.get(cacheKey)
    if (cached) {
      return { data: cached, loading: false, error: null }
    }
    return initialState
  })

  const refresh = React.useCallback(async () => {
    setState((prev) => ({ ...prev, loading: true, error: null }))
    try {
      const response = await fetchGlimsOverviewData(filters)
      overviewCache.set(cacheKey, response)
      setState({ data: response, loading: false, error: null })
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Unknown error'
      setState((prev) => ({ data: prev.data, loading: false, error: message }))
    }
  }, [cacheKey, filters])

  React.useEffect(() => {
    const cached = overviewCache.get(cacheKey)
    if (cached) {
      setState({ data: cached, loading: false, error: null })
      return
    }
    void refresh()
  }, [cacheKey, refresh])

  return { ...state, refresh }
}
