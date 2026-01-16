import { subDays } from 'date-fns'
import * as React from 'react'
import { DEFAULT_DATE_RANGE_DAYS } from '../../config'
import { formatDateInput, formatHoursToDuration, formatNumber } from '../../utils/format'
import type { OverviewFilters, TimeframeOption } from '../overview/types'
import { useGlimsTestsData } from './useGlimsTestsData'
import '../overview/overview.css'
import { ResponsiveContainer, BarChart, Bar, LineChart, Line, XAxis, YAxis, Tooltip, CartesianGrid, Legend } from 'recharts'

const TIMEFRAME_OPTIONS: Array<{ value: TimeframeOption; label: string }> = [
    { value: 'daily', label: 'Daily' },
    { value: 'weekly', label: 'Weekly' },
]

const TEST_TYPES = ['CN', 'MB', 'FFM', 'HM', 'HO', 'LW', 'MC', 'PN', 'RS', 'TP', 'PS', 'MY', 'WA']

const TEST_COLORS: Record<string, string> = {
    CN: '#38BDF8',
    MB: '#FB923C',
    FFM: '#4ADE80',
    HM: '#A855F7',
    HO: '#F472B6',
    LW: '#FACC15',
    MC: '#2DD4BF',
    PN: '#818CF8',
    RS: '#F87171',
    TP: '#34D399',
    PS: '#60A5FA',
    MY: '#FBBF24',
    WA: '#E879F9',
    Unknown: '#94A3B8',
}

function createInitialFilters(): OverviewFilters {
    const today = new Date()
    const from = subDays(today, DEFAULT_DATE_RANGE_DAYS - 1)
    return {
        dateFrom: formatDateInput(from),
        dateTo: formatDateInput(today),
        timeframe: 'daily',
    }
}

export function GlimsTestsTab() {
    const [filters, setFilters] = React.useState<OverviewFilters>(createInitialFilters)
    const [formFilters, setFormFilters] = React.useState<OverviewFilters>(filters)
    const [selectedTests, setSelectedTests] = React.useState<string[]>(TEST_TYPES)

    const { data, loading, error } = useGlimsTestsData(filters)

    const handleInputChange = (event: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
        const { name, value } = event.target
        setFormFilters((prev) => ({ ...prev, [name]: value }))
    }

    const handleTestToggle = (test: string) => {
        setSelectedTests((prev) =>
            prev.includes(test) ? prev.filter((t) => t !== test) : [...prev, test]
        )
    }

    const handleRefresh = () => {
        setFilters(formFilters)
    }

    // Pre-calculate segmented activity based on selected tests
    const segmentedActivity = React.useMemo(() => {
        return (
            data?.activity.map((point) => {
                const item: any = { label: point.label }
                selectedTests.forEach((test) => {
                    item[`prep_${test}`] = point.prepBreakdown[test] || 0
                    item[`start_${test}`] = point.startBreakdown[test] || 0
                })
                return item
            }) ?? []
        )
    }, [data, selectedTests])

    const lastUpdateLabel = React.useMemo(() => {
        return `Last update: ${new Date().toLocaleTimeString()}`
    }, [data])

    const dynamicKpis = React.useMemo(() => {
        if (!data) return { totalTests: 0, avgPrepToStartHours: null }

        let totalTests = 0
        let totalWeightedHours = 0
        let totalCountForAvg = 0

        selectedTests.forEach((test) => {
            const count = data.summary.testsByType[test] || 0
            const avg = data.summary.avgByType[test]

            totalTests += count
            if (avg !== undefined && avg !== null) {
                totalWeightedHours += avg * count
                totalCountForAvg += count
            }
        })

        const avgPrepToStartHours = totalCountForAvg > 0 ? totalWeightedHours / totalCountForAvg : null

        return { totalTests, avgPrepToStartHours }
    }, [data, selectedTests])

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
                </div>
            </section>

            {error && <div className="overview__error">Failed to load tests data: {error}</div>}

            <section className="overview__kpis">
                <KpiCard label="Total Tests" value={formatNumber(dynamicKpis.totalTests)} />
                <KpiCard
                    label="Avg Prep to Start"
                    value={formatHoursToDuration(dynamicKpis.avgPrepToStartHours)}
                    accent="highlight"
                />
            </section>

            <section className="overview__grid">
                <div className="overview__card overview__card--full">
                    <CardHeader title="PREP TO START TREND" subtitle="Evolution of the average time from preparation to start" />
                    <div className="overview__chart">
                        {data?.trend && data.trend.length > 0 ? (
                            <ResponsiveContainer width="100%" height={320}>
                                <LineChart data={data.trend}>
                                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(255, 255, 255, 0.08)" vertical={false} />
                                    <XAxis dataKey="label" stroke="var(--color-text-secondary)" tickLine={false} />
                                    <YAxis
                                        stroke="var(--color-text-secondary)"
                                        tickLine={false}
                                        axisLine={false}
                                        tickFormatter={(h) => formatHoursToDuration(h)}
                                    />
                                    <Tooltip
                                        wrapperStyle={{ zIndex: 1000 }}
                                        contentStyle={{
                                            background: '#0f1d3b',
                                            borderRadius: 12,
                                            border: '1px solid rgba(255,255,255,0.15)'
                                        }}
                                        labelStyle={{ color: '#f4f7ff', fontWeight: 700 }}
                                        formatter={(value: any) => [formatHoursToDuration(value), 'Duration']}
                                    />
                                    <Legend />
                                    <Line
                                        type="monotone"
                                        dataKey="avgHours"
                                        stroke="#38BDF8"
                                        strokeWidth={2}
                                        dot={false}
                                        name={filters.timeframe === 'weekly' ? 'Weekly Average' : 'Daily Average'}
                                    />
                                    <Line
                                        type="monotone"
                                        dataKey="movingAvgHours"
                                        stroke="#A855F7"
                                        strokeDasharray="4 4"
                                        strokeWidth={2}
                                        dot={false}
                                        name={filters.timeframe === 'weekly' ? 'Moving Average (14d)' : 'Moving Average (7d)'}
                                    />
                                </LineChart>
                            </ResponsiveContainer>
                        ) : (
                            <EmptyState loading={loading} />
                        )}
                    </div>
                </div>

                <div className="overview__card overview__card--half">
                    <CardHeader title="ANALYSIS PREP DATE" subtitle="Tests that started preparation (segmented by test type)" />
                    <div className="overview__chart">
                        {segmentedActivity.length > 0 ? (
                            <ResponsiveContainer width="100%" height={320}>
                                <BarChart data={segmentedActivity}>
                                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(255, 255, 255, 0.08)" vertical={false} />
                                    <XAxis dataKey="label" stroke="var(--color-text-secondary)" tickLine={false} />
                                    <YAxis stroke="var(--color-text-secondary)" tickLine={false} axisLine={false} />
                                    <Tooltip
                                        position={{ y: 0 }}
                                        wrapperStyle={{ zIndex: 1000 }}
                                        contentStyle={{
                                            background: '#0f1d3b',
                                            borderRadius: 12,
                                            border: '1px solid rgba(255,255,255,0.15)'
                                        }}
                                        itemStyle={{ padding: '0px' }}
                                        labelStyle={{ color: '#f4f7ff', marginBottom: '4px', fontWeight: 700 }}
                                    />
                                    <Legend />
                                    {selectedTests.map((test) => (
                                        <Bar
                                            key={`prep_${test}`}
                                            stackId="prep"
                                            dataKey={`prep_${test}`}
                                            name={test}
                                            fill={TEST_COLORS[test] || TEST_COLORS.Unknown}
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
                    <CardHeader title="ANALYSIS START DATE" subtitle="Tests that started running (segmented by test type)" />
                    <div className="overview__chart">
                        {segmentedActivity.length > 0 ? (
                            <ResponsiveContainer width="100%" height={320}>
                                <BarChart data={segmentedActivity}>
                                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(255, 255, 255, 0.08)" vertical={false} />
                                    <XAxis dataKey="label" stroke="var(--color-text-secondary)" tickLine={false} />
                                    <YAxis stroke="var(--color-text-secondary)" tickLine={false} axisLine={false} />
                                    <Tooltip
                                        position={{ y: 0 }}
                                        wrapperStyle={{ zIndex: 1000 }}
                                        contentStyle={{
                                            background: '#0f1d3b',
                                            borderRadius: 12,
                                            border: '1px solid rgba(255,255,255,0.15)'
                                        }}
                                        itemStyle={{ padding: '0px' }}
                                        labelStyle={{ color: '#f4f7ff', marginBottom: '4px', fontWeight: 700 }}
                                    />
                                    <Legend />
                                    {selectedTests.map((test) => (
                                        <Bar
                                            key={`start_${test}`}
                                            stackId="start"
                                            dataKey={`start_${test}`}
                                            name={test}
                                            fill={TEST_COLORS[test] || TEST_COLORS.Unknown}
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

            {/* Floating Filter Menu */}
            <aside className="overview__floating-filter">
                <h3 className="overview__floating-filter-title">Test Types</h3>
                <div className="overview__checkbox-group" style={{ maxHeight: '70vh', overflowY: 'auto', paddingRight: '4px' }}>
                    {TEST_TYPES.map((test) => (
                        <label key={test} className="overview__checkbox-label" style={{ padding: '8px 11px', gap: '6px' }}>
                            <input
                                type="checkbox"
                                checked={selectedTests.includes(test) || false}
                                onChange={() => handleTestToggle(test)}
                                style={{ width: '14px', height: '14px', minWidth: '14px' }}
                            />
                            <span className="overview__floating-dot" style={{
                                display: 'inline-block',
                                width: '5px',
                                height: '5px',
                                borderRadius: '50%',
                                backgroundColor: TEST_COLORS[test] || TEST_COLORS.Unknown,
                                marginRight: '1px'
                            }}></span>
                            <span style={{ fontSize: '0.5rem', fontWeight: 700 }}>{test}</span>
                        </label>
                    ))}
                </div>
            </aside>
        </div>
    )
}

// Reusable Components (Local copies for now, should be shared eventually)
function KpiCard({ label, value, accent = 'default' }: { label: string; value: string; accent?: string }) {
    return (
        <div className={`overview__kpi overview__kpi--${accent}`}>
            <span className="overview__kpi-label">{label}</span>
            <span className="overview__kpi-value">{value}</span>
        </div>
    )
}

function CardHeader({ title, subtitle }: { title: string; subtitle?: string }) {
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
            {loading ? 'Loading tests data...' : 'No activity found for the selected range'}
        </div>
    )
}
