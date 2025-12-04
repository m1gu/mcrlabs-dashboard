import { subDays } from 'date-fns'
import * as React from 'react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { DEFAULT_DATE_RANGE_DAYS } from '../../config'
import { formatDateInput, formatHoursToDuration, formatNumber } from '../../utils/format'
import type { IntervalOption, OperationalFilters } from './types'
import { useOperationalData } from './useOperationalData'
import '../overview/overview.css'
import './operational.css'
import { resolveOperationalStateClass } from './stateStyles'

const INTERVAL_OPTIONS: Array<{ value: IntervalOption; label: string }> = [
  { value: 'day', label: 'Daily' },
  { value: 'week', label: 'Weekly' },
]

function createInitialFilters(): OperationalFilters {
  const today = new Date()
  const from = subDays(today, DEFAULT_DATE_RANGE_DAYS - 1)
  return {
    dateFrom: formatDateInput(from),
    dateTo: formatDateInput(today),
    interval: 'day',
  }
}

export function OperationalEfficiencyTab() {
  const initialFilters = React.useMemo(createInitialFilters, [])
  const [formFilters, setFormFilters] = React.useState<OperationalFilters>(initialFilters)
  const [filters, setFilters] = React.useState<OperationalFilters>(initialFilters)

  const { data, loading, error, refresh } = useOperationalData(filters)

  const handleInputChange = (event: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    const { name, value } = event.target
    setFormFilters((prev) => ({
      ...prev,
      [name]: value,
    }))
  }

  const handleRefresh = () => {
    const unchanged =
      formFilters.dateFrom === filters.dateFrom &&
      formFilters.dateTo === filters.dateTo &&
      formFilters.interval === filters.interval

    if (unchanged) {
      void refresh()
    } else {
      setFilters(formFilters)
    }
  }

  const groupingLabel = React.useMemo(
    () => (filters.interval === 'week' ? 'Weekly aggregation' : 'Daily aggregation'),
    [filters.interval],
  )

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
            <span>Interval</span>
            <select name="interval" value={formFilters.interval} onChange={handleInputChange}>
              {INTERVAL_OPTIONS.map((option) => (
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
          <span>{groupingLabel}</span>
          {data?.throughput.length ? <span>{formatNumber(data.throughput.length)} data points</span> : null}
        </div>
      </section>

      {error && <div className="overview__error">Failed to load operational metrics: {error}</div>}

      <section className="overview__kpis">
        <KpiCard
          label="Avg lead time"
          value={formatHoursToDuration(data?.kpis.averageLeadTimeHours ?? null)}
          caption="Average completion time for orders"
        />
        <KpiCard
          label="Median lead time"
          value={formatHoursToDuration(data?.kpis.medianLeadTimeHours ?? null)}
          caption="Median completion time for orders"
        />
        <KpiCard
          label="Orders completed"
          value={formatNumber(data?.kpis.ordersCompleted ?? null)}
          caption="In the selected window"
        />
        <KpiCard
          label="Samples completed"
          value={formatNumber(data?.kpis.samplesCompleted ?? null)}
          caption="Completed samples in range"
        />
      </section>

      <section className="overview__grid">
        <div className="overview__card overview__card--full">
          <CardHeader
            title="Order throughput & completion"
            subtitle="Orders created and completed with average completion hours"
          />
          <div className="overview__chart">
            {data?.throughput.length ? (
              <ResponsiveContainer width="100%" height={340}>
                <ComposedChart data={data.throughput}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255, 255, 255, 0.08)" />
                  <XAxis dataKey="label" stroke="var(--color-text-secondary)" />
                  <YAxis
                    yAxisId="orders"
                    stroke="var(--color-text-secondary)"
                    tickLine={false}
                    axisLine={false}
                    label={{ value: 'Orders', angle: -90, position: 'insideLeft', fill: 'var(--color-text-secondary)' }}
                  />
                  <YAxis
                    yAxisId="hours"
                    orientation="right"
                    stroke="var(--color-text-secondary)"
                    tickLine={false}
                    axisLine={false}
                    label={{ value: 'Hours', angle: -90, position: 'insideRight', fill: 'var(--color-text-secondary)' }}
                  />
                  <Tooltip
                    contentStyle={{ background: '#0f1d3b', borderRadius: 12, border: '1px solid rgba(255,255,255,0.08)' }}
                    labelStyle={{ color: '#f4f7ff' }}
                  />
                  <Legend />
                  <Bar
                    yAxisId="orders"
                    dataKey="ordersCreated"
                    name="Orders created"
                    fill="#4C6EF5"
                    barSize={20}
                    radius={[6, 6, 0, 0]}
                  />
                  <Bar
                    yAxisId="orders"
                    dataKey="ordersCompleted"
                    name="Orders completed"
                    fill="#7EE787"
                    barSize={20}
                    radius={[6, 6, 0, 0]}
                  />
                  <Line
                    yAxisId="hours"
                    type="monotone"
                    dataKey="averageCompletionHours"
                    name="Avg completion (h)"
                    stroke="#FFB547"
                    strokeWidth={2}
                    dot={false}
                  />
                </ComposedChart>
              </ResponsiveContainer>
            ) : (
              <EmptyState loading={loading} />
            )}
          </div>
        </div>

        <div className="overview__card overview__card--full">
          <CardHeader
            title="Sample cycle time"
            subtitle="Completed samples and average cycle time in hours"
          />
          <div className="overview__chart">
            {data?.sampleCycle.length ? (
              <ResponsiveContainer width="100%" height={340}>
                <ComposedChart data={data.sampleCycle}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255, 255, 255, 0.08)" />
                  <XAxis dataKey="label" stroke="var(--color-text-secondary)" />
                  <YAxis
                    yAxisId="samples"
                    stroke="var(--color-text-secondary)"
                    tickLine={false}
                    axisLine={false}
                    label={{
                      value: 'Samples',
                      angle: -90,
                      position: 'insideLeft',
                      fill: 'var(--color-text-secondary)',
                    }}
                  />
                  <YAxis
                    yAxisId="hours"
                    orientation="right"
                    stroke="var(--color-text-secondary)"
                    tickLine={false}
                    axisLine={false}
                    label={{ value: 'Hours', angle: -90, position: 'insideRight', fill: 'var(--color-text-secondary)' }}
                  />
                  <Tooltip
                    contentStyle={{ background: '#0f1d3b', borderRadius: 12, border: '1px solid rgba(255,255,255,0.08)' }}
                    labelStyle={{ color: '#f4f7ff' }}
                  />
                  <Legend />
                  <Bar
                    yAxisId="samples"
                    dataKey="samplesCompleted"
                    name="Samples completed"
                    fill="#2EA043"
                    barSize={20}
                    radius={[6, 6, 0, 0]}
                  />
                  <Line
                    yAxisId="hours"
                    type="monotone"
                    dataKey="averageCycleHours"
                    name="Avg cycle (h)"
                    stroke="#8B5CF6"
                    strokeWidth={2}
                    dot={false}
                  />
                </ComposedChart>
              </ResponsiveContainer>
            ) : (
              <EmptyState loading={loading} />
            )}
          </div>
        </div>

        <div className="overview__card">
          <CardHeader
            title="Order funnel"
            subtitle="Distribution of orders by lifecycle stage"
          />
          <div className="overview__chart overview__chart--compact">
            {data?.orderFunnel.length ? (
              <ResponsiveContainer width="100%" height={300}>
                <BarChart data={data.orderFunnel} layout="vertical" margin={{ top: 8, left: 0, right: 8, bottom: 8 }}>
                  <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="rgba(255, 255, 255, 0.08)" />
                  <XAxis type="number" stroke="var(--color-text-secondary)" />
                  <YAxis
                    type="category"
                    dataKey="label"
                    width={140}
                    stroke="var(--color-text-secondary)"
                    tickLine={false}
                  />
                  <Tooltip
                    contentStyle={{ background: '#0f1d3b', borderRadius: 12, border: '1px solid rgba(255,255,255,0.08)' }}
                    labelStyle={{ color: '#f4f7ff' }}
                  />
                  <Bar dataKey="count" name="Orders" fill="#4C6EF5" radius={[0, 8, 8, 0]} barSize={18} />
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <EmptyState loading={loading} />
            )}
          </div>
        </div>

        <div className="overview__card">
          <CardHeader
            title="Cycle time by matrix"
            subtitle="Average sample cycle hours per matrix type"
          />
          <div className="overview__table-wrapper">
            <table>
              <thead>
                <tr>
                  <th>Matrix</th>
                  <th>Samples</th>
                  <th>Avg cycle</th>
                </tr>
              </thead>
              <tbody>
                {data?.matrixCycle.length ? (
                  data.matrixCycle.map((item) => (
                    <tr key={item.matrixType}>
                      <td>{item.matrixType}</td>
                      <td>{formatNumber(item.completedSamples)}</td>
                      <td>{formatHoursToDuration(item.averageHours)}</td>
                    </tr>
                  ))
                ) : (
                  <EmptyTable loading={loading} colSpan={3} />
                )}
              </tbody>
            </table>
          </div>
        </div>

        <div className="overview__card overview__card--full">
          <CardHeader title="Slowest orders" subtitle="Orders with the longest turnaround in the selected range" />
          <div className="overview__table-wrapper">
            <table>
              <thead>
                <tr>
                  <th>Order</th>
                  <th>Customer</th>
                  <th>Status</th>
                  <th>Completion</th>
                  <th>Age</th>
                </tr>
              </thead>
              <tbody>
                {data?.slowestOrders.length ? (
                  data.slowestOrders.map((order) => (
                    <tr key={order.orderId}>
                      <td className="operational__order-ref">{order.reference}</td>
                      <td>
                        <div>{order.customer}</div>
                        <div className="operational__table-subtle">#{order.orderId}</div>
                      </td>
                      <td>
                        {order.state !== '--' ? (
                          <span
                            className={`operational__state-pill ${resolveOperationalStateClass(order.state)}`}
                          >
                            {order.state}
                          </span>
                        ) : (
                          '--'
                        )}
                      </td>
                      <td>{formatHoursToDuration(order.completionHours)}</td>
                      <td>{formatHoursToDuration(order.ageHours)}</td>
                    </tr>
                  ))
                ) : (
                  <EmptyTable loading={loading} colSpan={5} />
                )}
              </tbody>
            </table>
          </div>
        </div>
      </section>
    </div>
  )
}

type KpiCardProps = {
  label: string
  value: string
  caption?: string
}

function KpiCard({ label, value, caption }: KpiCardProps) {
  return (
    <div className="overview__kpi">
      <span className="overview__kpi-label">{label}</span>
      <span className="overview__kpi-value">{value}</span>
      {caption && <span className="overview__kpi-subtitle">{caption}</span>}
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
  return <div className="overview__empty">{loading ? 'Loading data...' : 'No data available for the selected range'}</div>
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
