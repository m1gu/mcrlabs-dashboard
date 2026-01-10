import { subDays } from 'date-fns'
import * as React from 'react'
import { DEFAULT_DATE_RANGE_DAYS } from '../../config'
import { formatDateInput, formatDateLabel, formatDateMMDDYYYY, formatDateTimeLabel, formatHoursToDuration, formatNumber } from '../../utils/format'
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
    sampleType: 'All',
  }
}

const SAMPLE_TYPES = ['Adult Use', 'Medical', 'AU R&D']

const TYPE_COLORS: Record<string, { samples: string; tests: string; reports: string }> = {
  'Adult Use': { samples: '#3B82F6', tests: '#38BDF8', reports: '#FACC15' }, // Created: Azul, Tests: Celeste, Reported: Amarillo
  Medical: { samples: '#2DD4BF', tests: '#FB923C', reports: '#38BDF8' },    // Created: Aquamarina, Tests: Naranja, Reported: Celeste
  'AU R&D': { samples: '#4ADE80', tests: '#4ADE80', reports: '#A855F7' },   // Created: Verde, Tests: Verde, Reported: Lila
  Unknown: { samples: '#94A3B8', tests: '#64748B', reports: '#475569' },
}

export function GlimsOverviewTab() {
  const initialFilters = React.useMemo(createInitialFilters, [])
  const [formFilters, setFormFilters] = React.useState<OverviewFilters>(initialFilters)
  const [filters, setFilters] = React.useState<OverviewFilters>(initialFilters)

  // Local state for multi-select checkboxes
  const [selectedTypes, setSelectedTypes] = React.useState<string[]>(SAMPLE_TYPES)

  const { data, loading, error, refresh } = useGlimsOverviewData(filters)

  const handleInputChange = (event: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    const { name, value } = event.target
    setFormFilters((prev) => ({
      ...prev,
      [name]: value,
    }))
  }

  const handleTypeToggle = (type: string) => {
    setSelectedTypes((prev) => (prev.includes(type) ? prev.filter((t) => t !== type) : [...prev, type]))
  }

  const handleRefresh = () => {
    const isSameFilters =
      formFilters.dateFrom === filters.dateFrom &&
      formFilters.dateTo === filters.dateTo &&
      formFilters.timeframe === filters.timeframe

    if (isSameFilters) {
      void refresh()
    } else {
      setFilters({ ...formFilters, sampleType: 'All' })
    }
  }

  // Aggregate KPIs based on selected types
  const aggregatedKpis = React.useMemo(() => {
    const summary = data?.summary
    if (!summary) return null

    let samples = 0
    let tests = 0
    let reports = 0
    let totalTatWeight = 0
    let totalTatReports = 0

    selectedTypes.forEach((type) => {
      const typeReports = summary.reportsByType?.[type] || 0
      const typeTat = summary.tatByType?.[type] || 0

      samples += summary.samplesByType?.[type] || 0
      tests += summary.testsByType?.[type] || 0
      reports += typeReports

      if (typeTat > 0 && typeReports > 0) {
        totalTatWeight += typeTat * typeReports
        totalTatReports += typeReports
      }
    })

    const avgTatHours = totalTatReports > 0 ? totalTatWeight / totalTatReports : null

    return { samples, tests, reports, avgTatHours }
  }, [data, selectedTypes])

  // Prepare chart data with segmented keys
  const segmentedActivity = React.useMemo(() => {
    return (
      data?.dailyActivity.map((point) => {
        const item: any = { ...point }
        selectedTypes.forEach((type) => {
          const safeType = type.replace(/\s+/g, '_')
          item[`samples_${safeType}`] = point.samplesBreakdown?.[type] || 0
          item[`tests_${safeType}`] = point.testsBreakdown?.[type] || 0
          item[`reports_${safeType}`] = point.reportedBreakdown?.[type] || 0
        })
        return item
      }) ?? []
    )
  }, [data, selectedTypes])

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

      <aside className="overview__floating-filter">
        <h3 className="overview__floating-filter-title">Sample Type</h3>
        <div className="overview__checkbox-group">
          {SAMPLE_TYPES.map((type) => (
            <label key={type} className="overview__checkbox-label">
              <input type="checkbox" checked={selectedTypes.includes(type)} onChange={() => handleTypeToggle(type)} />
              <span>{type}</span>
            </label>
          ))}
        </div>
      </aside>

      {error && <div className="overview__error">Failed to load overview: {error}</div>}

      <section className="overview__kpis">
        <KpiCard label="Samples" value={formatNumber(aggregatedKpis?.samples ?? null)} />
        <KpiCard label="Tests" value={formatNumber(aggregatedKpis?.tests ?? null)} />
        <KpiCard label="New customers" value={formatNumber(data?.summary.customers ?? null)} />
        <KpiCard label="Reports (samples reported)" value={formatNumber(aggregatedKpis?.reports ?? null)} />
        <KpiCard
          label="Avg TAT"
          value={formatHoursToDuration(aggregatedKpis?.avgTatHours ?? null)}
          accent="highlight"
        />
      </section>

      <section className="overview__grid">
        <div className="overview__card overview__card--full">
          <CardHeader title="SAMPLES" subtitle="Daily count of samples created and reported (segmented by type)" />
          <div className="overview__chart">
            {segmentedActivity.length > 0 ? (
              <ResponsiveContainer width="100%" height={320}>
                <BarChart data={segmentedActivity}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255, 255, 255, 0.08)" vertical={false} />
                  <XAxis dataKey="label" stroke="var(--color-text-secondary)" tickLine={false} />
                  <YAxis stroke="var(--color-text-secondary)" tickLine={false} axisLine={false} />
                  <Tooltip
                    contentStyle={{ background: '#0f1d3b', borderRadius: 12, border: '1px solid rgba(255,255,255,0.08)' }}
                    labelStyle={{ color: '#f4f7ff' }}
                  />
                  <Legend />
                  {selectedTypes.map((type) => (
                    <Bar
                      key={`samples_${type}`}
                      stackId="samples"
                      dataKey={`samples_${type.replace(/\s+/g, '_')}`}
                      name={`Samples (${type})`}
                      fill={TYPE_COLORS[type]?.samples || TYPE_COLORS.Unknown.samples}
                    />
                  ))}
                  {selectedTypes.map((type) => (
                    <Bar
                      key={`reports_${type}`}
                      stackId="reports"
                      dataKey={`reports_${type.replace(/\s+/g, '_')}`}
                      name={`Reported (${type})`}
                      fill={TYPE_COLORS[type]?.reports || TYPE_COLORS.Unknown.reports}
                    />
                  ))}
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <EmptyState loading={loading} />
            )}
          </div>
        </div>

        <div className="overview__card overview__card--full">
          <CardHeader title="TESTS" subtitle="Daily count of tests completed (segmented by type)" />
          <div className="overview__chart">
            {segmentedActivity.length > 0 ? (
              <ResponsiveContainer width="100%" height={320}>
                <BarChart data={segmentedActivity}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255, 255, 255, 0.08)" vertical={false} />
                  <XAxis dataKey="label" stroke="var(--color-text-secondary)" tickLine={false} />
                  <YAxis stroke="var(--color-text-secondary)" tickLine={false} axisLine={false} />
                  <Tooltip
                    contentStyle={{ background: '#0f1d3b', borderRadius: 12, border: '1px solid rgba(255,255,255,0.08)' }}
                    labelStyle={{ color: '#f4f7ff' }}
                  />
                  <Legend />
                  {selectedTypes.map((type) => (
                    <Bar
                      key={`tests_${type}`}
                      stackId="tests"
                      dataKey={`tests_${type.replace(/\s+/g, '_')}`}
                      name={`Tests (${type})`}
                      fill={TYPE_COLORS[type]?.tests || TYPE_COLORS.Unknown.tests}
                    />
                  ))}
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
                      <td>{formatDateMMDDYYYY(customer.createdAt)}</td>
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
          <CardHeader title="Types of tests most requested" subtitle="Distribution by assay type (filtered by selection)" />
          <div className="overview__chart overview__chart--compact">
            {data?.testsByLabel?.length ? (
              <ResponsiveContainer width="100%" height={320}>
                <BarChart
                  data={data.testsByLabel.map((item) => {
                    const row: any = { label: item.label }
                    selectedTypes.forEach((type) => {
                      row[type] = item.breakdown?.[type] || 0
                    })
                    return row
                  })}
                  layout="vertical"
                  margin={{ left: 2, right: 8 }}
                >
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
                  <Legend />
                  {selectedTypes.map((type) => (
                    <Bar
                      key={type}
                      stackId="tests"
                      dataKey={type}
                      name={type}
                      fill={TYPE_COLORS[type]?.tests || TYPE_COLORS.Unknown.tests}
                      barSize={14}
                    />
                  ))}
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
  children?: React.ReactNode
}

function CardHeader({ title, subtitle, children }: CardHeaderProps) {
  return (
    <header className="overview__card-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
      <div>
        <h2>{title}</h2>
        {subtitle && <p>{subtitle}</p>}
      </div>
      {children}
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
