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
