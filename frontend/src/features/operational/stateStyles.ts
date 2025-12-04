export const STATE_VARIANT_MAP: Record<string, string> = {
  'NOT STARTED': 'state-pill--pending',
  'ON HOLD': 'state-pill--warning',
  'IN PROGRESS': 'state-pill--progress',
  RUNNING: 'state-pill--progress',
  BATCHED: 'state-pill--info',
  WEIGHED: 'state-pill--info',
  'NEEDS REVIEW (DATA TEAM)': 'state-pill--review',
  'NEEDS REVIEW (LAB)': 'state-pill--review',
  'NEEDS SECOND CHECK': 'state-pill--review',
  'SECOND CHECK DONE': 'state-pill--info',
  RERUN: 'state-pill--danger',
  'RE-PREP': 'state-pill--danger',
  COMPLETED: 'state-pill--success',
  'NOT REPORTABLE': 'state-pill--neutral',
  REPORTED: 'state-pill--reported',
  'REPORTABLE/PARTIAL': 'state-pill--info',
  APPROVED: 'state-pill--success',
}

export function resolveOperationalStateClass(state: string | null | undefined): string {
  if (!state || state === '--') return 'state-pill--default'
  const key = state.toUpperCase()
  if (STATE_VARIANT_MAP[key]) return STATE_VARIANT_MAP[key]
  if (key.includes('REVIEW')) return 'state-pill--review'
  if (key.includes('HOLD')) return 'state-pill--warning'
  return 'state-pill--default'
}
