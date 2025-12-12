import * as React from 'react'
import type { PrioritySamplesData, PrioritySamplesFilters } from './types'
import { fetchPrioritySamples } from './api'

type State = {
  data: PrioritySamplesData | null
  loading: boolean
  error: string | null
}

const initialState: State = {
  data: null,
  loading: false,
  error: null,
}

const cache = new Map<string, PrioritySamplesData>()

function cacheKey(filters: PrioritySamplesFilters) {
  return JSON.stringify(filters)
}

export function usePrioritySamples(filters: PrioritySamplesFilters) {
  const [state, setState] = React.useState<State>(initialState)

  const load = React.useCallback(async () => {
    const key = cacheKey(filters)
    const cached = cache.get(key)
    if (cached) {
      setState({ data: cached, loading: false, error: null })
      return
    }
    setState((prev) => ({ ...prev, loading: true, error: null }))
    try {
      const data = await fetchPrioritySamples(filters)
      cache.set(key, data)
      setState({ data, loading: false, error: null })
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to load priority samples'
      setState({ data: null, loading: false, error: message })
    }
  }, [filters])

  React.useEffect(() => {
    void load()
  }, [load])

  const refresh = React.useCallback(async () => {
    cache.clear()
    return load()
  }, [load])

  return { ...state, refresh }
}
