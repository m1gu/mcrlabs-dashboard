type StatusPillProps = {
  value?: string | null
  compact?: boolean
}

function getStatusClass(value?: string | null): string {
  if (!value) return ''
  const normalized = value.toLowerCase()
  if (normalized === 'completed') return 'priority__status-pill priority__status-pill--completed'
  if (normalized === 'batched') return 'priority__status-pill priority__status-pill--batched'

  if (normalized.includes('waiting for sample')) return 'priority__status-pill priority__status-pill--waiting'
  if (normalized.includes('sample received')) return 'priority__status-pill priority__status-pill--received'
  if (normalized === 'running') return 'priority__status-pill priority__status-pill--running'
  if (normalized === 'generating') return 'priority__status-pill priority__status-pill--generating'
  if (normalized.includes('needs metrc upload')) return 'priority__status-pill priority__status-pill--metrc'
  if (normalized.includes('retest') || normalized.includes('reprep')) return 'priority__status-pill priority__status-pill--retest'
  if (normalized === 'reported') return 'priority__status-pill priority__status-pill--reported'
  if (normalized === 'destroyed') return 'priority__status-pill priority__status-pill--destroyed'
  if (normalized === 'cancelled') return 'priority__status-pill priority__status-pill--cancelled'
  if (normalized.includes('not reportable')) return 'priority__status-pill priority__status-pill--not-reportable'
  if (normalized.includes('needs second check')) return 'priority__status-pill priority__status-pill--needs-check'
  if (normalized.includes('second check done')) return 'priority__status-pill priority__status-pill--check-done'

  return 'priority__status-pill'
}

export function StatusPill({ value, compact = false }: StatusPillProps) {
  if (!value) return compact ? <span className="priority__status-pill">--</span> : <span className="priority__status-pill">No status</span>
  return <span className={getStatusClass(value)}>{value}</span>
}
