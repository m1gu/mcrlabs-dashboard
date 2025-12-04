import { format, parseISO } from 'date-fns'

export function parseApiDate(value: string | null | undefined): Date | null {
  if (!value) return null
  try {
    return parseISO(value)
  } catch {
    return null
  }
}

export function formatDateInput(date: Date): string {
  return format(date, 'yyyy-MM-dd')
}

export function formatApiDateTimeUtc(date: Date): string {
  const iso = date.toISOString()
  const [base, fractionalWithZ = '000Z'] = iso.split('.')
  const fractional = fractionalWithZ.replace('Z', '').padEnd(6, '0')
  return `${base}.${fractional}+00:00`
}

export function formatDateLabel(date: Date): string {
  return format(date, 'MMM dd')
}

export function formatDateTimeLabel(date: Date | null): string {
  if (!date) return '--'
  return format(date, 'yyyy-MM-dd HH:mm')
}

export function formatDateTimeShort(date: Date | null): string {
  if (!date) return '--'
  return format(date, 'MM-dd-yyyy HH:mm')
}

export function formatNumber(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '--'
  return new Intl.NumberFormat('en-US').format(value)
}

export function formatHoursToDuration(hours: number | null | undefined): string {
  if (hours === null || hours === undefined || Number.isNaN(hours) || hours <= 0) {
    return '--'
  }

  const totalHours = Math.round(hours)
  const days = Math.floor(totalHours / 24)
  const remainingHours = totalHours % 24

  if (days > 0) {
    return `${days} d ${remainingHours} h`
  }

  return `${remainingHours} h`
}

export function formatElapsedDaysHours(from: Date | null, to: Date = new Date()): string {
  if (!from) {
    return '--'
  }

  const diffMs = Math.max(to.getTime() - from.getTime(), 0)
  const totalHours = Math.floor(diffMs / (1000 * 60 * 60))
  const days = Math.floor(totalHours / 24)
  const hours = totalHours % 24

  if (days > 0) {
    return `${days}d${hours}h`
  }

  return `${hours}h`
}
