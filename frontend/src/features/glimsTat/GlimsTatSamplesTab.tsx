import { parseISO, subDays } from 'date-fns'
import * as React from 'react'
import {
  formatDateInput,
  formatDateTimeLabel,
  formatHoursToDuration,
  formatNumber,
} from '../../utils/format'
import type { GlimsTatFilters } from './types'
import { useGlimsTat } from './useGlimsTat'
import '../priority/priority.css'
import '../overview/overview.css'

const DEFAULT_LOOKBACK_DAYS = 7
const DEFAULT_MIN_OPEN_HOURS = 72
const DEFAULT_THRESHOLD_HOURS = 120

function computeRange(days: number) {
  const end = new Date()
  const start = subDays(end, Math.max(1, days))
  return {
    from: formatDateInput(start),
    to: formatDateInput(end),
  }
}

type FormState = {
  days: number
  dispensaryQuery: string
  minOpenHours: number
  thresholdHours: number
}

export function GlimsTatSamplesTab() {
  const [formState, setFormState] = React.useState<FormState>({
    days: DEFAULT_LOOKBACK_DAYS,
    dispensaryQuery: '',
    minOpenHours: DEFAULT_MIN_OPEN_HOURS,
    thresholdHours: DEFAULT_THRESHOLD_HOURS,
  })
  const initialRange = React.useMemo(() => computeRange(DEFAULT_LOOKBACK_DAYS), [])
  const [filters, setFilters] = React.useState<GlimsTatFilters>({
    dateFrom: initialRange.from,
    dateTo: initialRange.to,
    dispensaryQuery: '',
    minOpenHours: DEFAULT_MIN_OPEN_HOURS,
    thresholdHours: DEFAULT_THRESHOLD_HOURS,
  })
  const [activeDays, setActiveDays] = React.useState<number>(DEFAULT_LOOKBACK_DAYS)
  const { data, loading, error, refresh } = useGlimsTat(filters, { lookbackDays: activeDays })
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

  const handleDispensaryChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const { value } = event.target
    setFormState((prev) => ({ ...prev, dispensaryQuery: value }))
  }

  const applyFilters = () => {
    const normalizedDays = Math.max(1, formState.days || DEFAULT_LOOKBACK_DAYS)
    const range = computeRange(normalizedDays)
    const nextFilters: GlimsTatFilters = {
      dateFrom: range.from,
      dateTo: range.to,
      dispensaryQuery: formState.dispensaryQuery.trim(),
      minOpenHours: formState.minOpenHours,
      thresholdHours: formState.thresholdHours,
    }

    const unchanged =
      filters.dateFrom === nextFilters.dateFrom &&
      filters.dateTo === nextFilters.dateTo &&
      filters.dispensaryQuery === nextFilters.dispensaryQuery &&
      filters.minOpenHours === nextFilters.minOpenHours &&
      filters.thresholdHours === nextFilters.thresholdHours

    if (unchanged) {
      void refresh()
    } else {
      setFilters(nextFilters)
      setActiveDays(normalizedDays)
    }
  }

  const rangeLabel = React.useMemo(
    () => `${formatDateInput(parseISO(filters.dateFrom))} - ${formatDateInput(parseISO(filters.dateTo))}`,
    [filters.dateFrom, filters.dateTo],
  )
  const rows = data?.samples ?? []
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
            <span>Dispensary (ID o nombre)</span>
            <input
              type="text"
              name="dispensaryQuery"
              value={formState.dispensaryQuery}
              onChange={handleDispensaryChange}
            />
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

      {error && <div className="overview__error">Failed to load TAT samples: {error}</div>}

      <div className="overview__card">
        <header className="overview__card-header">
          <h2>Top Slowest Samples to Report</h2>
          <p>Reported GLIMS samples with the longest open time in the selected window</p>
        </header>
        <div className="priority__slow-header">
          <div className="priority__slow-kpis">
            <KpiCard label="Avg open time" value={formatDurationValue(stats?.averageOpenHours)} caption="Received → reported" />
            <KpiCard label="95th percentile" value={formatDurationValue(stats?.percentile95OpenHours)} caption="Outlier reference" />
            <KpiCard
              label="Outlier threshold"
              value={formatDurationValue(stats?.thresholdHours ?? formState.thresholdHours)}
              caption={`Samples listed: ${stats?.totalSamples ?? 0}`}
            />
          </div>
        </div>
        <div className="overview__table-wrapper priority__table priority__table--slow">
          <table>
            <thead>
              <tr>
                <th>Sample</th>
                <th>Dispensary</th>
                <th>Received</th>
                <th>Reported</th>
                <th>Open time</th>
                <th>Open time (hrs)</th>
                <th>Tests</th>
              </tr>
            </thead>
            <tbody>
              {rows.length ? (
                rows.map((sample) => (
                  <tr
                    key={sample.sampleId}
                    className={sample.isOutlier ? 'priority__slow-row priority__slow-row--outlier' : 'priority__slow-row'}
                  >
                    <td className="priority__order-ref">{sample.sampleId}</td>
                    <td>{sample.dispensaryName || '--'}</td>
                    <td>{sample.dateReceived ? formatDateTimeLabel(sample.dateReceived) : '--'}</td>
                    <td>{sample.reportDate ? formatDateTimeLabel(sample.reportDate) : '--'}</td>
                    <td>
                      <div className="priority__slow-open">
                        <span>{sample.openTimeLabel}</span>
                        {sample.isOutlier ? <span className="priority__slow-flag">Outlier</span> : null}
                      </div>
                    </td>
                    <td>{formatNumber(sample.openTimeHours)}</td>
                    <td>{sample.testsCount}</td>
                  </tr>
                ))
              ) : (
                <EmptyTable loading={loading} colSpan={7} />
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
