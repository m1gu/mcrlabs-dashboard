import { subDays } from 'date-fns'
import * as React from 'react'
import { DEFAULT_DATE_RANGE_DAYS } from '../../config'
import { formatDateInput, formatDateLabel, formatDateMMDDYYYY, formatDateTimeLabel, formatHoursToDuration, formatNumber } from '../../utils/format'
import type { OverviewFilters, TimeframeOption } from '../overview/types'
import { useGlimsOverviewData } from './useGlimsOverviewData'
import { useGlimsCustomers } from './useGlimsCustomers'
import '../overview/overview.css'
import { ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid, Legend, AreaChart, Area, Line, LineChart, ReferenceLine } from 'recharts'

const TIMEFRAME_OPTIONS: Array<{ value: TimeframeOption; label: string }> = [
  { value: 'daily', label: 'Daily' },
  { value: 'weekly', label: 'Weekly' },
  { value: 'monthly', label: 'Monthly' },
]

function createInitialFilters(): OverviewFilters {
  const today = new Date()
  const from = subDays(today, DEFAULT_DATE_RANGE_DAYS - 1)
  return {
    dateFrom: formatDateInput(from),
    dateTo: formatDateInput(today),
    timeframe: 'daily',
    sampleType: 'All',
    customerId: null,
  }
}

const SAMPLE_TYPES = ['Adult Use', 'Medical', 'AU R&D', 'Unknown']

const TYPE_COLORS: Record<string, { samples: string; tests: string; reports: string }> = {
  'Adult Use': { samples: '#38BDF8', tests: '#38BDF8', reports: '#38BDF8' }, // Celeste
  Medical: { samples: '#FB923C', tests: '#FB923C', reports: '#FB923C' },    // Naranja
  'AU R&D': { samples: '#4ADE80', tests: '#4ADE80', reports: '#4ADE80' },   // Verde
  Unknown: { samples: '#94A3B8', tests: '#64748B', reports: '#475569' },
}

export function GlimsOverviewTab() {
  const initialFilters = React.useMemo(createInitialFilters, [])
  const [formFilters, setFormFilters] = React.useState<OverviewFilters>(initialFilters)
  const [filters, setFilters] = React.useState<OverviewFilters>(initialFilters)

  // Local state for multi-select checkboxes
  const [selectedTypes, setSelectedTypes] = React.useState<string[]>(SAMPLE_TYPES)

  // Hook for customer list
  const { customers, loading: customersLoading } = useGlimsCustomers(formFilters.dateFrom, formFilters.dateTo)

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
      formFilters.timeframe === filters.timeframe &&
      formFilters.customerId === filters.customerId

    if (isSameFilters) {
      void refresh()
    } else {
      setFilters({ ...formFilters, sampleType: 'All' })
    }
  }

  const handleCustomerChange = (event: React.ChangeEvent<HTMLSelectElement>) => {
    const value = event.target.value
    const customerId = value === '' ? null : parseInt(value, 10)

    // Update formFilters
    setFormFilters((prev) => ({
      ...prev,
      customerId,
    }))

    // Auto-refresh: update filters immediately
    setFilters((prev) => ({
      ...prev,
      customerId,
    }))
  }

  // Reset customer selection if the customer is no longer in the filtered list
  React.useEffect(() => {
    if (formFilters.customerId && customers.length > 0 && !customersLoading) {
      const exists = customers.some((c) => c.id === formFilters.customerId)
      if (!exists) {
        setFormFilters((prev) => ({ ...prev, customerId: null }))
        setFilters((prev) => ({ ...prev, customerId: null }))
      }
    }
  }, [customers, customersLoading, formFilters.customerId])

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

  // Aggregate TAT data based on selected types
  const aggregatedTatDaily = React.useMemo(() => {
    if (!data?.tatDaily) return []

    const points = data.tatDaily.map((point) => {
      let withinSla = 0
      let beyondSla = 0
      let totalWeight = 0
      let totalReports = 0

      selectedTypes.forEach((type) => {
        const typeWithin = point.withinBreakdown?.[type] || 0
        const typeBeyond = point.beyondBreakdown?.[type] || 0
        const typeHours = (point as any).hours_breakdown?.[type] || 0

        withinSla += typeWithin
        beyondSla += typeBeyond

        const typeReports = typeWithin + typeBeyond
        if (typeReports > 0 && typeHours > 0) {
          totalWeight += typeHours * typeReports
          totalReports += typeReports
        }
      })

      const averageHours = totalReports > 0 ? totalWeight / totalReports : null

      return {
        ...point,
        withinSla,
        beyondSla,
        averageHours,
      }
    })

    // Re-calculate moving average for the aggregated data
    const windowSize = filters.timeframe === 'weekly' ? 14 : 7
    return points.map((point, idx) => {
      const start = Math.max(0, idx - windowSize + 1)
      const window = points.slice(start, idx + 1)
      const values = window.map((p) => p.averageHours).filter((v): v is number => v !== null)
      const movingAverageHours = values.length > 0 ? values.reduce((a, b) => a + b, 0) / values.length : null
      return { ...point, movingAverageHours }
    })
  }, [data, selectedTypes, filters.timeframe])

  const lastUpdateLabel = React.useMemo(() => {
    if (!data?.summary.lastUpdatedAt) return 'No update timestamp available'
    return `Last update: ${formatDateTimeLabel(data.summary.lastUpdatedAt)}`
  }, [data])

  return (
    <div className="overview">


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
        <div className="overview__card overview__card--half">
          <CardHeader title="TAT BY VOLUME" subtitle="Daily count of samples within vs above target" />
          <div className="overview__chart">
            {aggregatedTatDaily.length > 0 ? (
              <ResponsiveContainer width="100%" height={320}>
                <AreaChart data={aggregatedTatDaily}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255, 255, 255, 0.08)" vertical={false} />
                  <XAxis dataKey="label" stroke="var(--color-text-secondary)" tickLine={false} />
                  <YAxis stroke="var(--color-text-secondary)" tickLine={false} axisLine={false} />
                  <Tooltip
                    contentStyle={{ background: '#0f1d3b', borderRadius: 12, border: '1px solid rgba(255,255,255,0.08)' }}
                    labelStyle={{ color: '#f4f7ff' }}
                  />
                  <Legend />
                  <Area
                    type="monotone"
                    dataKey="withinSla"
                    stackId="1"
                    stroke="#2EA043"
                    fill="rgba(46, 160, 67, 0.65)"
                    name="Within target"
                  />
                  <Area
                    type="monotone"
                    dataKey="beyondSla"
                    stackId="1"
                    stroke="#F85149"
                    fill="rgba(248, 81, 73, 0.55)"
                    name="Above target"
                  />
                </AreaChart>
              </ResponsiveContainer>
            ) : (
              <EmptyState loading={loading} />
            )}
          </div>
        </div>

        <div className="overview__card overview__card--half">
          <CardHeader title="DAILY TAT TREND" subtitle="Daily average and moving average duration" />
          <div className="overview__chart">
            {aggregatedTatDaily.length > 0 ? (
              <ResponsiveContainer width="100%" height={320}>
                <LineChart data={aggregatedTatDaily}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255, 255, 255, 0.08)" vertical={false} />
                  <XAxis dataKey="label" stroke="var(--color-text-secondary)" tickLine={false} />
                  <YAxis
                    stroke="var(--color-text-secondary)"
                    tickLine={false}
                    axisLine={false}
                    tickFormatter={(val) => formatHoursToDuration(val)}
                    width={70}
                  />
                  <Tooltip
                    contentStyle={{ background: '#0f1d3b', borderRadius: 12, border: '1px solid rgba(255,255,255,0.08)' }}
                    labelStyle={{ color: '#f4f7ff' }}
                    formatter={(value: any) => formatHoursToDuration(value)}
                  />
                  <Legend />
                  <Line
                    type="monotone"
                    dataKey="averageHours"
                    stroke="#7EE787"
                    strokeWidth={2}
                    dot={false}
                    name="Daily avg (h)"
                  />
                  <Line
                    type="monotone"
                    dataKey="movingAverageHours"
                    stroke="#8B5CF6"
                    strokeDasharray="4 4"
                    strokeWidth={2}
                    dot={false}
                    name="Moving avg (h)"
                  />
                  <ReferenceLine y={72} stroke="#FFD166" strokeDasharray="5 5" label="Target 72h" />
                </LineChart>
              </ResponsiveContainer>
            ) : (
              <EmptyState loading={loading} />
            )}
          </div>
        </div>

        <div className="overview__card overview__card--half">
          <CardHeader title="SAMPLES CREATED" subtitle="Daily count of samples created (segmented by type)" />
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
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <EmptyState loading={loading} />
            )}
          </div>
        </div>

        <div className="overview__card overview__card--half">
          <CardHeader title="SAMPLES REPORTED" subtitle="Daily count of samples reported (segmented by type)" />
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
      </section>

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
          <label className="overview__control">
            <span>Customer</span>
            <select
              name="customerId"
              value={formFilters.customerId ?? ''}
              onChange={handleCustomerChange}
              disabled={customersLoading}
              style={{ minWidth: '200px' }}
            >
              <option value="">All Customers</option>
              {customers.map((customer) => (
                <option key={customer.id} value={customer.id}>
                  {customer.name}
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
