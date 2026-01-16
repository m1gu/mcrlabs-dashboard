import * as React from 'react'
import type { GlimsTestsData, GlimsTestsFilters } from './types'
import { fetchGlimsTestsData } from './api'

type UseTestsDataState = {
    data: GlimsTestsData | null
    loading: boolean
    error: string | null
}

const initialState: UseTestsDataState = {
    data: null,
    loading: false,
    error: null,
}

const testsCache = new Map<string, GlimsTestsData>()

export function useGlimsTestsData(filters: GlimsTestsFilters) {
    const cacheKey = React.useMemo(() => JSON.stringify(filters), [filters])
    const [state, setState] = React.useState<UseTestsDataState>(() => {
        const cached = testsCache.get(cacheKey)
        if (cached) {
            return { data: cached, loading: false, error: null }
        }
        return initialState
    })

    const refresh = React.useCallback(async () => {
        setState((prev) => ({ ...prev, loading: true, error: null }))
        try {
            const response = await fetchGlimsTestsData(filters)
            testsCache.set(cacheKey, response)
            setState({ data: response, loading: false, error: null })
        } catch (err) {
            const message = err instanceof Error ? err.message : 'Unknown error'
            setState((prev) => ({ data: prev.data, loading: false, error: message }))
        }
    }, [cacheKey, filters])

    React.useEffect(() => {
        const cached = testsCache.get(cacheKey)
        if (cached) {
            setState({ data: cached, loading: false, error: null })
            return
        }
        void refresh()
    }, [cacheKey, refresh])

    return { ...state, refresh }
}
