import { parseISO, subDays } from 'date-fns'
import * as React from 'react'
import {
  formatApiDateTimeUtc,
  formatDateInput,
  formatDateTimeLabel,
  formatHoursToDuration,
  formatNumber,
} from '../../utils/format'
import type { TatFilters } from './types'
import { useTatOrders } from './useTatOrders'
import '../priority/priority.css'
import '../overview/overview.css'

const DEFAULT_LOOKBACK_DAYS = 7
const DEFAULT_MIN_OPEN_HOURS = 72
const DEFAULT_THRESHOLD_HOURS = 120
const DEFAULT_TAT_RANGE = computeRange(DEFAULT_LOOKBACK_DAYS)

function computeRange(days: number) {
  const end = new Date()
  const start = subDays(end, Math.max(1, days))
  return {
    from: formatApiDateTimeUtc(start),
    to: formatApiDateTimeUtc(end),
  }
}

type FormState = {
  days: number
  customerQuery: string
  minOpenHours: number
  thresholdHours: number
}

export function TatOrdersTab() {
  const [formState, setFormState] = React.useState<FormState>({
    days: DEFAULT_LOOKBACK_DAYS,
    customerQuery: '',
    minOpenHours: DEFAULT_MIN_OPEN_HOURS,
    thresholdHours: DEFAULT_THRESHOLD_HOURS,
  })
  const initialRange = DEFAULT_TAT_RANGE
  const [filters, setFilters] = React.useState<TatFilters>({
    dateFrom: initialRange.from,
    dateTo: initialRange.to,
    customerQuery: '',
    minOpenHours: DEFAULT_MIN_OPEN_HOURS,
    thresholdHours: DEFAULT_THRESHOLD_HOURS,
  })
  const [activeDays, setActiveDays] = React.useState<number>(DEFAULT_LOOKBACK_DAYS)
  const { data, loading, error, refresh } = useTatOrders(filters, { lookbackDays: activeDays })
  const [lastUpdated, setLastUpdated] = React.useState<Date | null>(null)

  React.useEffect(() => {
    if (data) {
      setLastUpdated(new Date())
    }
  }, [data])

  const handleNumberChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value } = event.target
    const parsed = Number.parseInt(value || '0', 10)
    setFormState((prev) => ({
      ...prev,
      [name]: Number.isNaN(parsed) ? prev[name as keyof FormState] : parsed,
    }))
  }

  const handleCustomerChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const { value } = event.target
    setFormState((prev) => ({ ...prev, customerQuery: value }))
  }

  const applyFilters = () => {
    const normalizedDays = Math.max(1, formState.days || DEFAULT_LOOKBACK_DAYS)
    const range = computeRange(normalizedDays)
    const nextFilters: TatFilters = {
      dateFrom: range.from,
      dateTo: range.to,
      customerQuery: formState.customerQuery.trim(),
      minOpenHours: formState.minOpenHours,
      thresholdHours: formState.thresholdHours,
    }

    const unchanged =
      filters.dateFrom === nextFilters.dateFrom &&
      filters.dateTo === nextFilters.dateTo &&
      filters.customerQuery === nextFilters.customerQuery &&
      filters.minOpenHours === nextFilters.minOpenHours &&
      filters.thresholdHours === nextFilters.thresholdHours

    if (unchanged) {
      void refresh()
    } else {
      setFilters(nextFilters)
      setActiveDays(normalizedDays)
    }
  }

  const rangeLabel = React.useMemo(() => `${formatDateInput(parseISO(filters.dateFrom))} - ${formatDateInput(parseISO(filters.dateTo))}`, [filters.dateFrom, filters.dateTo])
  const rows = data?.orders ?? []
  const stats = data?.stats

  return (
    <div className="overview">
      <section className="priority__controls">
        <div className="priority__control-meta">
          <span className="priority__meta-label">
            Range:
            <strong> {rangeLabel}</strong>
          </span>
          <span className="priority__meta-label">
            Last refresh:
            <strong> {lastUpdated ? formatDateTimeLabel(lastUpdated) : '--'}</strong>
          </span>
        </div>
        <div className="priority__control-inputs">
          <label className="priority__field">
            <span>Lookback days</span>
            <input
              type="number"
              name="days"
              min={1}
              step={1}
              value={formState.days}
              onChange={handleNumberChange}
            />
          </label>
          <label className="priority__field">
            <span>Customer (ID or name)</span>
            <input type="text" name="customerQuery" value={formState.customerQuery} onChange={handleCustomerChange} />
          </label>
          <label className="priority__field">
            <span>Open time ≥ (hours)</span>
            <input
              type="number"
              name="minOpenHours"
              min={0}
              step={1}
              value={formState.minOpenHours}
              onChange={handleNumberChange}
            />
          </label>
          <label className="priority__field">
            <span>Outlier threshold (hours)</span>
            <input
              type="number"
              name="thresholdHours"
              min={0}
              step={1}
              value={formState.thresholdHours}
              onChange={handleNumberChange}
            />
          </label>
          <button className="priority__refresh" type="button" onClick={applyFilters} disabled={loading}>
            {loading ? 'Refreshing...' : 'Update list'}
          </button>
        </div>
      </section>

      {error && <div className="overview__error">Failed to load TAT orders: {error}</div>}

      <div className="overview__card">
        <header className="overview__card-header">
          <h2>Top Slowest Orders to Report</h2>
          <p>Reported orders with the longest open time in the selected window</p>
        </header>
        <div className="priority__slow-header">
          <div className="priority__slow-kpis">
            <KpiCard label="Avg open time" value={formatDurationValue(stats?.averageOpenHours)} caption="Created → reported" />
            <KpiCard label="95th percentile" value={formatDurationValue(stats?.percentile95OpenHours)} caption="Outlier reference" />
            <KpiCard
              label="Outlier threshold"
              value={formatDurationValue(stats?.thresholdHours ?? formState.thresholdHours)}
              caption={`Orders listed: ${stats?.totalOrders ?? 0}`}
            />
          </div>
        </div>
        <div className="overview__table-wrapper priority__table priority__table--slow">
          <table>
            <thead>
              <tr>
                <th>Order</th>
                <th>Customer</th>
                <th>Created</th>
                <th>Reported</th>
                <th>Open time</th>
                <th>Open time (hrs)</th>
                <th>Samples</th>
                <th>Tests</th>
              </tr>
            </thead>
            <tbody>
              {rows.length ? (
                rows.map((order) => (
                  <tr key={order.id} className={order.isOutlier ? 'priority__slow-row priority__slow-row--outlier' : 'priority__slow-row'}>
                    <td className="priority__order-ref">{order.reference}</td>
                    <td>{order.customer}</td>
                    <td>{formatDateTimeLabel(order.createdAt)}</td>
                    <td>{formatDateTimeLabel(order.reportedAt)}</td>
                    <td>
                      <div className="priority__slow-open">
                        <span>{order.openTimeLabel}</span>
                        {order.isOutlier ? <span className="priority__slow-flag">Outlier</span> : null}
                      </div>
                    </td>
                    <td>{formatNumber(order.openTimeHours)}</td>
                    <td>{order.samplesCount}</td>
                    <td>{order.testsCount}</td>
                  </tr>
                ))
              ) : (
                <EmptyTable loading={loading} colSpan={8} />
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}

function formatDurationValue(hours: number | null | undefined): string {
  if (hours === null || hours === undefined) return '--'
  return formatHoursToDuration(hours)
}

type KpiCardProps = {
  label: string
  value: string
  caption?: string
  accent?: 'default' | 'alert'
}

function KpiCard({ label, value, caption, accent = 'default' }: KpiCardProps) {
  const className = accent === 'alert' ? 'overview__kpi overview__kpi--highlight' : 'overview__kpi'
  return (
    <div className={className}>
      <span className="overview__kpi-label">{label}</span>
      <span className="overview__kpi-value">{value}</span>
      {caption && <span className="overview__kpi-subtitle">{caption}</span>}
    </div>
  )
}

function EmptyTable({ loading, colSpan }: { loading: boolean; colSpan: number }) {
  return (
    <tr>
      <td colSpan={colSpan} className="overview__empty">
        {loading ? 'Loading...' : 'No records'}
      </td>
    </tr>
  )
}
