export function formatDateTime(value: string | null | undefined) {
  if (!value) return '—'
  return new Intl.DateTimeFormat('es-PA', { dateStyle: 'medium', timeStyle: 'short' }).format(
    new Date(value),
  )
}

/** Fecha sin hora (YYYY-MM-DD) sin desfase de zona horaria. */
export function formatDate(value: string | null | undefined) {
  if (!value) return '—'
  const [y, m, d] = value.split('-').map(Number)
  return new Intl.DateTimeFormat('es-PA', { dateStyle: 'medium' }).format(new Date(y, m - 1, d))
}

/** Montos en balboas (B/.), equivalentes 1:1 al dólar. */
export function formatMoney(value: string | number | null | undefined, decimals = 2) {
  if (value === null || value === undefined || value === '') return '—'
  return `B/. ${new Intl.NumberFormat('es-PA', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(Number(value))}`
}

const TZ = 'America/Panama'

/** Fecha de una marca de tiempo en la zona horaria de la empresa (Panamá). */
export function formatDay(value: string | null | undefined) {
  if (!value) return '—'
  return new Intl.DateTimeFormat('es-PA', {
    weekday: 'short',
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    timeZone: TZ,
  }).format(new Date(value))
}

/** Hora (con segundos) en la zona horaria de la empresa. */
export function formatTime(value: string | null | undefined) {
  if (!value) return '—'
  return new Intl.DateTimeFormat('es-PA', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
    timeZone: TZ,
  }).format(new Date(value))
}

/** YYYY-MM-DD y HH:MM de una marca de tiempo en la zona de la empresa (para formularios). */
export function toLocalParts(value: string): { date: string; time: string } {
  const parts = Object.fromEntries(
    new Intl.DateTimeFormat('en-CA', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
      timeZone: TZ,
    })
      .formatToParts(new Date(value))
      .map((p) => [p.type, p.value]),
  )
  return {
    date: `${parts.year}-${parts.month}-${parts.day}`,
    time: `${parts.hour}:${parts.minute}`,
  }
}

/** Minutos como horas "8:30". */
export function formatMinutes(value: number | null | undefined) {
  if (!value) return '—'
  return `${Math.floor(value / 60)}:${String(value % 60).padStart(2, '0')}`
}

/** Hora corta (HH:MM) en la zona de la empresa. */
export function formatHour(value: string | null | undefined) {
  if (!value) return '—'
  return new Intl.DateTimeFormat('es-PA', {
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
    timeZone: TZ,
  }).format(new Date(value))
}
