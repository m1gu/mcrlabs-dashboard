import { subDays } from 'date-fns'
import * as React from 'react'
import { DEFAULT_DATE_RANGE_DAYS } from '../../config'
import { formatDateInput, formatDateLabel, formatDateTimeLabel, formatHoursToDuration, formatNumber } from '../../utils/format'
import type { OverviewFilters, TimeframeOption } from '../overview/types'
import { useGlimsOverviewData } from './useGlimsOverviewData'
import '../overview/overview.css'
import { ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid, Legend, AreaChart, Area, Line, ReferenceLine } from 'recharts'

const TIMEFRAME_OPTIONS: Array<{ value: TimeframeOption; label: string }> = [
  { value: 'daily', label: 'Daily' },
  { value: 'weekly', label: 'Weekly' },
]

function createInitialFilters(): OverviewFilters {
  const today = new Date()
  const from = subDays(today, DEFAULT_DATE_RANGE_DAYS - 1)
  return {
    dateFrom: formatDateInput(from),
    dateTo: formatDateInput(today),
    timeframe: 'daily',
  }
}

export function GlimsOverviewTab() {
  const initialFilters = React.useMemo(createInitialFilters, [])
  const [formFilters, setFormFilters] = React.useState<OverviewFilters>(initialFilters)
  const [filters, setFilters] = React.useState<OverviewFilters>(initialFilters)

  const { data, loading, error, refresh } = useGlimsOverviewData(filters)

  const handleInputChange = (event: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    const { name, value } = event.target
    setFormFilters((prev) => ({
      ...prev,
      [name]: value,
    }))
  }

  const handleRefresh = () => {
    const isSameFilters =
      formFilters.dateFrom === filters.dateFrom &&
      formFilters.dateTo === filters.dateTo &&
      formFilters.timeframe === filters.timeframe

    if (isSameFilters) {
      void refresh()
    } else {
      setFilters(formFilters)
    }
  }

  const lastUpdateLabel = React.useMemo(() => {
    if (!data?.summary.lastUpdatedAt) return 'No update timestamp available'
    return `Last update: ${formatDateTimeLabel(data.summary.lastUpdatedAt)}`
  }, [data])

  return (
    <div className="overview">
      <section className="overview__controls">
        <div className="overview__control-group">
          <label className="overview__control">
            <span>From</span>
            <input
              type="date"
              name="dateFrom"
              value={formFilters.dateFrom}
              max={formFilters.dateTo}
              onChange={handleInputChange}
            />
          </label>
          <label className="overview__control">
            <span>To</span>
            <input
              type="date"
              name="dateTo"
              value={formFilters.dateTo}
              min={formFilters.dateFrom}
              onChange={handleInputChange}
            />
          </label>
          <label className="overview__control">
            <span>Timeframe</span>
            <select name="timeframe" value={formFilters.timeframe} onChange={handleInputChange}>
              {TIMEFRAME_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
          <button className="overview__refresh-button" type="button" onClick={handleRefresh} disabled={loading}>
            {loading ? 'Refreshing...' : 'Refresh'}
          </button>
        </div>
        <div className="overview__status">
          <span>{lastUpdateLabel}</span>
          {data?.summary.rangeStart && data?.summary.rangeEnd && (
            <span>
              Range: {formatDateLabel(data.summary.rangeStart)} to {formatDateLabel(data.summary.rangeEnd)}
            </span>
          )}
        </div>
      </section>

      {error && <div className="overview__error">Failed to load overview: {error}</div>}

      <section className="overview__kpis">
        <KpiCard label="Samples" value={formatNumber(data?.summary.samples ?? null)} />
        <KpiCard label="Tests" value={formatNumber(data?.summary.tests ?? null)} />
        <KpiCard label="New customers" value={formatNumber(data?.summary.customers ?? null)} />
        <KpiCard label="Reports (samples reported)" value={formatNumber(data?.summary.reports ?? null)} />
        <KpiCard label="Avg TAT" value={formatHoursToDuration(data?.summary.avgTatHours ?? null)} accent="highlight" />
      </section>

      <section className="overview__grid">
        <div className="overview__card overview__card--full">
          <CardHeader
            title="Samples vs Tests"
            subtitle="Daily count of samples created, tests completed, and samples reported"
          />
          <div className="overview__chart">
            {data?.dailyActivity && data.dailyActivity.length > 0 ? (
              <ResponsiveContainer width="100%" height={320}>
                <BarChart data={data.dailyActivity}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255, 255, 255, 0.08)" vertical={false} />
                  <XAxis dataKey="label" stroke="var(--color-text-secondary)" tickLine={false} />
                  <YAxis stroke="var(--color-text-secondary)" tickLine={false} axisLine={false} />
                  <Tooltip
                    contentStyle={{ background: '#0f1d3b', borderRadius: 12, border: '1px solid rgba(255,255,255,0.08)' }}
                    labelStyle={{ color: '#f4f7ff' }}
                  />
                  <Legend />
                  {/* Generate stacked bars for samples breakdown */}
                  {(() => {
                    const sampleKeys = new Set<string>()
                    data.dailyActivity.forEach((day: any) => {
                      Object.keys(day).forEach((key) => {
                        if (key.startsWith('samples_')) {
                          sampleKeys.add(key)
                        }
                      })
                    })
                    const sortedKeys = Array.from(sampleKeys).sort()

                    const colors = ['#FFD43B', '#22B8CF', '#FF922B']

                    if (sortedKeys.length === 0) {
                      return <Bar dataKey="samples" name="Samples" fill="#4C6EF5" radius={[6, 6, 0, 0]} />
                    }

                    return sortedKeys.map((key, index) => {
                      const label = key.replace('samples_', '')
                      // Only top bar gets radius
                      const isLast = index === sortedKeys.length - 1
                      const radius: [number, number, number, number] = isLast ? [6, 6, 0, 0] : [0, 0, 0, 0]
                      return (
                        <Bar
                          key={key}
                          dataKey={key}
                          name={`Samples (${label})`}
                          fill={colors[index % colors.length]}
                          stackId="samples"
                          radius={radius}
                        />
                      )
                    })
                  })()}
                  <Bar dataKey="tests" name="Tests" fill="#7EE787" radius={[6, 6, 0, 0]} />
                  <Bar dataKey="testsReported" name="Samples reported" fill="#F472B6" radius={[6, 6, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <EmptyState loading={loading} />
            )}
          </div>
        </div>

        <div className="overview__card">
          <CardHeader title="New customers" subtitle="Latest customers within the selected range" />
          <div className="overview__table-wrapper">
            <table>
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Name</th>
                  <th>Created</th>
                </tr>
              </thead>
              <tbody>
                {data?.newCustomers?.length ? (
                  data.newCustomers.map((customer) => (
                    <tr key={customer.id}>
                      <td>{customer.id}</td>
                      <td>{customer.name}</td>
                      <td>{formatDateInput(customer.createdAt)}</td>
                    </tr>
                  ))
                ) : (
                  <EmptyTable loading={loading} colSpan={3} />
                )}
              </tbody>
            </table>
          </div>
        </div>

        <div className="overview__card">
          <CardHeader title="Top 10 customers with the most tests" subtitle="Sorted by total tests in the period" />
          <div className="overview__table-wrapper">
            <table>
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Name</th>
                  <th>Tests</th>
                  <th>Reported</th>
                </tr>
              </thead>
              <tbody>
                {data?.topCustomers?.length ? (
                  data.topCustomers.map((customer) => (
                    <tr key={customer.id}>
                      <td>{customer.id}</td>
                      <td>{customer.name}</td>
                      <td>{formatNumber(customer.tests)}</td>
                      <td>{formatNumber(customer.testsReported)}</td>
                    </tr>
                  ))
                ) : (
                  <EmptyTable loading={loading} colSpan={4} />
                )}
              </tbody>
            </table>
          </div>
        </div>

        <div className="overview__card">
          <CardHeader title="Types of tests most requested" subtitle="Distribution by assay type" />
          <div className="overview__chart overview__chart--compact">
            {data?.testsByLabel?.length ? (
              <ResponsiveContainer width="100%" height={320}>
                <BarChart data={data.testsByLabel} layout="vertical" margin={{ left: 2, right: 8 }}>
                  <XAxis type="number" stroke="var(--color-text-secondary)" />
                  <YAxis
                    type="category"
                    dataKey="label"
                    stroke="var(--color-text-secondary)"
                    width={38}
                    tickLine={false}
                    tick={{ fontSize: 10 }}
                  />
                  <Tooltip
                    contentStyle={{ background: '#0f1d3b', borderRadius: 12, border: '1px solid rgba(255,255,255,0.08)' }}
                    labelStyle={{ color: '#f4f7ff' }}
                  />
                  <Bar dataKey="count" name="Tests" fill="#7EE787" radius={[0, 8, 8, 0]} barSize={14} />
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <EmptyState loading={loading} />
            )}
          </div>
        </div>

        <div className="overview__card overview__card--full">
          <CardHeader title="Daily TAT trend" subtitle="Average hours and TAT compliance per day" />
          <div className="overview__chart">
            {data?.tatDaily?.length ? (
              <ResponsiveContainer width="100%" height={340}>
                <AreaChart data={data.tatDaily}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255, 255, 255, 0.08)" />
                  <XAxis dataKey="label" stroke="var(--color-text-secondary)" />
                  <YAxis
                    yAxisId="counts"
                    orientation="left"
                    stroke="var(--color-text-secondary)"
                    tickLine={false}
                    axisLine={false}
                    width={60}
                    label={{ value: 'Tests', angle: -90, position: 'insideLeft', fill: 'var(--color-text-secondary)' }}
                  />
                  <YAxis
                    yAxisId="hours"
                    orientation="right"
                    stroke="var(--color-text-secondary)"
                    tickLine={false}
                    axisLine={false}
                    width={60}
                    label={{ value: 'Hours', angle: -90, position: 'insideRight', fill: 'var(--color-text-secondary)' }}
                  />
                  <Tooltip
                    contentStyle={{ background: '#0f1d3b', borderRadius: 12, border: '1px solid rgba(255,255,255,0.08)' }}
                    labelStyle={{ color: '#f4f7ff' }}
                  />
                  <Legend />
                  <Area
                    yAxisId="counts"
                    type="monotone"
                    dataKey="withinSla"
                    stackId="1"
                    stroke="#2EA043"
                    fill="rgba(46, 160, 67, 0.65)"
                    name="Within target"
                  />
                  <Area
                    yAxisId="counts"
                    type="monotone"
                    dataKey="beyondSla"
                    stackId="1"
                    stroke="#F85149"
                    fill="rgba(248, 81, 73, 0.55)"
                    name="Above target"
                  />
                  <Line
                    yAxisId="hours"
                    type="monotone"
                    dataKey="averageHours"
                    stroke="#7EE787"
                    strokeWidth={2}
                    dot={false}
                    name="Daily avg (h)"
                  />
                  <Line
                    yAxisId="hours"
                    type="monotone"
                    dataKey="movingAverageHours"
                    stroke="#8B5CF6"
                    strokeDasharray="4 4"
                    strokeWidth={2}
                    dot={false}
                    name="Moving avg (h)"
                  />
                  <ReferenceLine yAxisId="hours" y={72} stroke="#FFD166" strokeDasharray="5 5" label="Target 72h" />
                </AreaChart>
              </ResponsiveContainer>
            ) : (
              <EmptyState loading={loading} />
            )}
          </div>
        </div>
      </section>
    </div>
  )
}

type KpiCardProps = {
  label: string
  value: string
  subtitle?: string
  accent?: 'default' | 'highlight'
}

function KpiCard({ label, value, subtitle, accent = 'default' }: KpiCardProps) {
  return (
    <div className={`overview__kpi overview__kpi--${accent}`}>
      <span className="overview__kpi-label">{label}</span>
      <span className="overview__kpi-value">{value}</span>
      {subtitle && <span className="overview__kpi-subtitle">{subtitle}</span>}
    </div>
  )
}

type CardHeaderProps = {
  title: string
  subtitle?: string
}

function CardHeader({ title, subtitle }: CardHeaderProps) {
  return (
    <header className="overview__card-header">
      <h2>{title}</h2>
      {subtitle && <p>{subtitle}</p>}
    </header>
  )
}

function EmptyState({ loading }: { loading: boolean }) {
  return (
    <div className="overview__empty">
      {loading ? 'Loading data...' : 'No data available for the selected range'}
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
