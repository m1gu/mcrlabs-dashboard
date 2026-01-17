import * as React from 'react'
import { fetchGlimsCustomersList } from './api'

interface Customer {
    id: number
    name: string
}

export function useGlimsCustomers(dateFrom: string, dateTo: string) {
    const [customers, setCustomers] = React.useState<Customer[]>([])
    const [loading, setLoading] = React.useState(false)
    const [error, setError] = React.useState<string | null>(null)

    React.useEffect(() => {
        let cancelled = false

        async function fetch() {
            setLoading(true)
            setError(null)
            try {
                const response = await fetchGlimsCustomersList(dateFrom, dateTo)
                if (!cancelled) {
                    setCustomers(response.customers)
                }
            } catch (err) {
                if (!cancelled) {
                    setError(err instanceof Error ? err.message : 'Error loading customers')
                }
            } finally {
                if (!cancelled) {
                    setLoading(false)
                }
            }
        }

        fetch()
        return () => { cancelled = true }
    }, [dateFrom, dateTo])

    return { customers, loading, error }
}
