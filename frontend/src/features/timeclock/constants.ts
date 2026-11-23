export const DIRECTIONS: [string, string][] = [
  ['in', 'Entrada'],
  ['out', 'Salida'],
  ['unknown', 'Sin tipo'],
]

export const SOURCES: [string, string][] = [
  ['device', 'Reloj'],
  ['file', 'Archivo'],
  ['manual', 'Manual'],
  ['app', 'App móvil'],
]

export const BATCH_STATUS: Record<
  string,
  { label: string; variant: 'success' | 'neutral' | 'danger' }
> = {
  pending: { label: 'En cola', variant: 'neutral' },
  processing: { label: 'Procesando', variant: 'neutral' },
  preview: { label: 'Lista para confirmar', variant: 'neutral' },
  confirmed: { label: 'Confirmada', variant: 'success' },
  reverted: { label: 'Revertida', variant: 'danger' },
  discarded: { label: 'Descartada', variant: 'neutral' },
  failed: { label: 'Error', variant: 'danger' },
}

export function daysAgoISO(days: number) {
  const d = new Date()
  d.setDate(d.getDate() - days)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

export const WORKDAY_STATUS: Record<
  string,
  { label: string; variant: 'success' | 'neutral' | 'danger' }
> = {
  pending: { label: 'Por aprobar', variant: 'neutral' },
  review: { label: 'Con inconsistencias', variant: 'danger' },
  approved: { label: 'Aprobada', variant: 'success' },
}

export const WEEKDAYS: [number, string][] = [
  [0, 'Lun'],
  [1, 'Mar'],
  [2, 'Mié'],
  [3, 'Jue'],
  [4, 'Vie'],
  [5, 'Sáb'],
  [6, 'Dom'],
]

/** Lunes de la semana actual (YYYY-MM-DD). */
export function mondayISO() {
  const d = new Date()
  d.setDate(d.getDate() - ((d.getDay() + 6) % 7))
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}
