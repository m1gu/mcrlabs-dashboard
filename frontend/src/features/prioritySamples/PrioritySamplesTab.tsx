import * as React from 'react'
import {
  formatDateInput,
  formatHoursToDays,
  parseApiDate,
} from '../../utils/format'
import { usePrioritySamples } from './usePrioritySamples'
import type { PrioritySamplesFilters } from './types'
import '../priority/priority.css'
import './priority.css'
import '../overview/overview.css'
import { StatusPill } from './StatusPill'

const DEFAULT_MIN_DAYS = 3
const DEFAULT_TAT_HOURS = 120

function createFilters(): PrioritySamplesFilters {
  return {
    minDaysOverdue: DEFAULT_MIN_DAYS,
    tatHours: DEFAULT_TAT_HOURS,
  }
}

export function PrioritySamplesTab() {
  const [filters, setFilters] = React.useState<PrioritySamplesFilters>(createFilters)
  const [form, setForm] = React.useState<PrioritySamplesFilters>(filters)
  const { data, loading, error, refresh } = usePrioritySamples(filters)
  const [expandedSampleId, setExpandedSampleId] = React.useState<string | null>(null)

  const handleNumberChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value } = event.target
    const parsed = Number.parseInt(value || '0', 10)
    setForm((prev) => ({ ...prev, [name]: Number.isNaN(parsed) ? prev[name as keyof PrioritySamplesFilters] : parsed }))
  }

  const applyFilters = () => {
    const unchanged = form.minDaysOverdue === filters.minDaysOverdue && form.tatHours === filters.tatHours
    if (unchanged) {
      void refresh()
    } else {
      setFilters(form)
    }
  }

  return (
    <div className="overview priority">
      <section className="overview__controls">
        <div className="overview__control-group">
          <label className="overview__control">
            <span>Minimum days overdue</span>
            <input
              type="number"
              name="minDaysOverdue"
              min={0}
              value={form.minDaysOverdue}
              onChange={handleNumberChange}
              aria-label="Minimum days overdue"
            />
          </label>
          <label className="overview__control">
            <span>TAT (hours)</span>
            <input
              type="number"
              name="tatHours"
              min={0}
              value={form.tatHours}
              onChange={handleNumberChange}
              aria-label="TAT hours"
            />
          </label>
          <button className="overview__refresh-button" type="button" onClick={applyFilters} disabled={loading}>
            {loading ? 'Refreshing...' : 'Refresh'}
          </button>
        </div>
      </section>

      {error && <div className="overview__error">Failed to load priority samples: {error}</div>}

      <section className="overview__grid">
        <div className="overview__card overview__card--full">
          <CardHeader
            title="Most overdue samples"
            subtitle="Open time descending. Tests complete when analytes is present."
          />
          {data?.samples?.length ? (
            <div className="priority__accordion">
              <div className="priority__accordion-header priority__accordion-header--samples">
                <span />
                <span>Sample</span>
                <span>Customer</span>
                <span>Status</span>
                <span>Received</span>
                <span>Open time</span>
                <span>TAT breach</span>
                <span>Tests</span>
              </div>
              {data.samples.map((sample) => {
                const openLabel = sample.openHours != null ? formatHoursToDays(sample.openHours) : '--'
                const completion = sample.testsTotal > 0 ? `${sample.testsComplete}/${sample.testsTotal}` : '0/0'
                const receivedLabel = sample.dateReceived ? formatDateInput(parseApiDate(sample.dateReceived)!) : '--'
                const expanded = expandedSampleId === sample.sampleId
                const breachThreshold = filters.tatHours ?? DEFAULT_TAT_HOURS
                const tatBreach = sample.openHours != null && sample.openHours >= breachThreshold
                const toggle = () => setExpandedSampleId(expanded ? null : sample.sampleId)
                return (
                  <div
                    key={sample.sampleId}
                    className={`priority__accordion-item priority__accordion-item--sample ${expanded ? 'priority__accordion-item--open' : ''
                      } ${tatBreach ? 'priority__accordion-item--breach' : ''}`}
                  >
                    <button type="button" className="priority__accordion-trigger" onClick={toggle}>
                      <div className="priority__sample-row priority__sample-row--single">
                        <span className={`priority__chevron ${expanded ? 'is-open' : ''}`}>{expanded ? '▾' : '▸'}</span>
                        <span className="priority__metrc-sample-id">{sample.sampleId}</span>
                        <span className="priority__cell--ellipsis">{sample.clientName || sample.dispensaryName || '--'}</span>
                        <StatusPill value={sample.status} />
                        <span>{receivedLabel}</span>
                        <span>{openLabel}</span>
                        <span className={`priority__sla-chip ${tatBreach ? 'priority__sla-chip--breach' : ''}`}>
                          {tatBreach ? 'Yes' : 'No'}
                        </span>
                        <span className="priority__pill">{completion} tests</span>
                      </div>
                    </button>
                    {expanded && (
                      <div className="priority__sample-content">
                        <div className="priority__test-table-wrapper">
                          <table className="priority__test-table">
                            <thead>
                              <tr>
                                <th>Label</th>
                                <th>Start date</th>
                                <th>Status</th>
                              </tr>
                            </thead>
                            <tbody>
                              {sample.tests.length ? (
                                sample.tests.map((t) => (
                                  <tr key={`${sample.sampleId}-${t.label}-${t.startDate || 'nodate'}`}>
                                    <td>{t.label}</td>
                                    <td>{t.startDate ? formatDateInput(parseApiDate(t.startDate)!) : '--'}</td>
                                    <td><StatusPill value={t.status} compact /></td>
                                  </tr>
                                ))
                              ) : (
                                <tr>
                                  <td colSpan={3} className="priority__empty">
                                    No tests
                                  </td>
                                </tr>
                              )}
                            </tbody>
                          </table>
                        </div>
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          ) : (
            <EmptyState loading={loading} message="No overdue samples" />
          )}
        </div>

        <div className="overview__card overview__card--full">
          <CardHeader title="METRC samples (last 30 days)" subtitle="Samples with METRC status linked by metrc_id" />
          <div className="priority__table priority__table--metrc">
            <table>
              <thead>
                <tr>
                  <th>Sample</th>
                  <th>Customer</th>
                  <th>METRC ID</th>
                  <th>Status</th>
                  <th>Open time</th>
                </tr>
              </thead>
              <tbody>
                {data?.metrcSamples?.length ? (
                  data.metrcSamples.map((row) => (
                    <tr key={row.id}>
                      <td className="priority__metrc-sample-id">{row.customId}</td>
                      <td>{row.customer}</td>
                      <td className="priority__metrc-id">{row.metrcId}</td>
                      <td>
                        <span
                          className={`priority__status-chip ${row.metrcStatus && row.metrcStatus.toLowerCase().includes('progress')
                            ? 'priority__status-chip--warning'
                            : 'priority__status-chip--default'
                            }`}
                        >
                          {row.metrcStatus}
                        </span>
                      </td>
                      <td>{row.openTime || '--'}</td>
                    </tr>
                  ))
                ) : (
                  <EmptyRow loading={loading} colSpan={5} />
                )}
              </tbody>
            </table>
          </div>
        </div>
      </section>
    </div>
  )
}

function EmptyState({ loading, message }: { loading: boolean; message: string }) {
  return <div className="priority__empty">{loading ? 'Loading...' : message}</div>
}

function EmptyRow({ loading, colSpan }: { loading: boolean; colSpan: number }) {
  return (
    <tr>
      <td colSpan={colSpan} className="priority__empty">
        {loading ? 'Loading...' : 'No records'}
      </td>
    </tr>
  )
}

type CardHeaderProps = {
  title: string
  subtitle?: string
}

function CardHeader({ title, subtitle }: CardHeaderProps) {
  return (
    <div className="overview__card-header">
      <div>
        <h3>{title}</h3>
        {subtitle && <p>{subtitle}</p>}
      </div>
    </div>
  )
}
