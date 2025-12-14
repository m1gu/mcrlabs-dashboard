type StatusPillProps = {
  value?: string | null
  compact?: boolean
}

function getStatusClass(value?: string | null): string {
  if (!value) return ''
  const normalized = value.toLowerCase()
  if (normalized === 'completed') return 'priority__status-pill priority__status-pill--completed'
  if (normalized === 'batched') return 'priority__status-pill priority__status-pill--batched'
  return 'priority__status-pill'
}

export function StatusPill({ value, compact = false }: StatusPillProps) {
  if (!value) return compact ? <span className="priority__status-pill">--</span> : <span className="priority__status-pill">No status</span>
  return <span className={getStatusClass(value)}>{value}</span>
}
