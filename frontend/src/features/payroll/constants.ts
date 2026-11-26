type Variant = 'success' | 'neutral' | 'danger'

export const RUN_STATUS: Record<string, { label: string; variant: Variant }> = {
  draft: { label: 'Borrador', variant: 'neutral' },
  calculated: { label: 'Calculada', variant: 'neutral' },
  approved: { label: 'Aprobada', variant: 'success' },
  paid: { label: 'Pagada', variant: 'success' },
  cancelled: { label: 'Anulada', variant: 'danger' },
}

const pad = (n: number) => String(n).padStart(2, '0')
export const isoDate = (d: Date) =>
  `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`

/** Período sugerido según la frecuencia: la semana pasada, la quincena o el mes en curso. */
export function suggestedPeriod(frequency: string): { start: string; end: string; pay: string } {
  const now = new Date()
  if (frequency === 'weekly') {
    const monday = new Date(now)
    monday.setDate(now.getDate() - ((now.getDay() + 6) % 7) - 7)
    const sunday = new Date(monday)
    sunday.setDate(monday.getDate() + 6)
    const friday = new Date(sunday)
    friday.setDate(sunday.getDate() + 5)
    return { start: isoDate(monday), end: isoDate(sunday), pay: isoDate(friday) }
  }
  const y = now.getFullYear()
  const m = now.getMonth()
  const last = new Date(y, m + 1, 0).getDate()
  if (frequency === 'biweekly' && now.getDate() <= 15) {
    return {
      start: isoDate(new Date(y, m, 1)),
      end: isoDate(new Date(y, m, 15)),
      pay: isoDate(new Date(y, m, 15)),
    }
  }
  const start = frequency === 'biweekly' ? 16 : 1
  return {
    start: isoDate(new Date(y, m, start)),
    end: isoDate(new Date(y, m, last)),
    pay: isoDate(new Date(y, m, last)),
  }
}

/** Las tres partidas del décimo del año (inicio, fin, pago). */
export function decimoPeriods(
  year: number,
): { label: string; start: string; end: string; pay: string }[] {
  return [
    {
      label: `1ª partida (16/12/${year - 1} – 15/04/${year})`,
      start: `${year - 1}-12-16`,
      end: `${year}-04-15`,
      pay: `${year}-04-15`,
    },
    {
      label: `2ª partida (16/04 – 15/08/${year})`,
      start: `${year}-04-16`,
      end: `${year}-08-15`,
      pay: `${year}-08-15`,
    },
    {
      label: `3ª partida (16/08 – 15/12/${year})`,
      start: `${year}-08-16`,
      end: `${year}-12-15`,
      pay: `${year}-12-15`,
    },
  ]
}
