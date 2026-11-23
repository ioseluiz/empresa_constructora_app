import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { jsonResponse, renderWithProviders } from '@/test/utils'
import { WorkDaysPage } from './workdays-page'

const base = {
  employee: 'e1',
  employee_code: 'E-0001',
  employee_name: 'Carlos Batista',
  project: 'p1',
  project_code: 'P-001',
  shift_name: 'Diurno',
  day_kind: 'regular',
  day_kind_display: 'Laborable',
  jornada: 'day',
  jornada_display: 'Diurna',
  segments: [],
  worked_minutes: 0,
  break_minutes: 0,
  ordinary_minutes: 0,
  overtime_day_minutes: 0,
  overtime_night_minutes: 0,
  overtime_mixed_minutes: 0,
  overtime_minutes: 0,
  late_minutes: 0,
  missing_minutes: 0,
  issues: [],
  issue_labels: [],
  blocking: false,
  status: 'pending',
  status_display: 'Por aprobar',
}
const ok = {
  ...base,
  id: 'w1',
  date: '2026-11-16',
  first_in: '2026-11-16T12:00:00Z',
  last_out: '2026-11-16T23:40:00Z',
  ordinary_minutes: 480,
  overtime_day_minutes: 120,
  overtime_mixed_minutes: 30,
  overtime_minutes: 150,
}
const blocked = {
  ...base,
  id: 'w2',
  date: '2026-11-17',
  first_in: '2026-11-17T12:00:00Z',
  last_out: null,
  issues: ['missing_out'],
  issue_labels: ['Falta la salida'],
  blocking: true,
  status: 'review',
  status_display: 'Con inconsistencias',
}

function mockApi(permissions: string[]) {
  const fetchMock = vi.fn((url: string, init?: RequestInit) => {
    if (url.includes('/iam/me/')) return Promise.resolve(jsonResponse({ permissions, roles: [] }))
    if (url.includes('/projects/'))
      return Promise.resolve(jsonResponse({ count: 0, next: null, previous: null, results: [] }))
    if (url.includes('/summary/'))
      return Promise.resolve(
        jsonResponse({
          total: 2,
          review: 1,
          pending: 1,
          approved: 0,
          worked_minutes: 630,
          ordinary_minutes: 480,
          overtime_minutes: 150,
        }),
      )
    if (init?.method === 'POST') return Promise.resolve(jsonResponse({ approved: 1 }))
    return Promise.resolve(
      jsonResponse({ count: 2, next: null, previous: null, results: [ok, blocked] }),
    )
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

describe('WorkDaysPage', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('muestra horas, extras por tipo e impide seleccionar jornadas incompletas', async () => {
    const fetchMock = mockApi(['timeclock.view', 'timeclock.approve'])
    renderWithProviders(<WorkDaysPage />)
    expect(await screen.findAllByText('Carlos Batista')).toHaveLength(2)
    expect(screen.getByText('07:00 – 18:40')).toBeInTheDocument()
    expect(screen.getAllByText('2:30')).toHaveLength(2) // tarjeta de resumen y fila
    expect(screen.getByText('M 0:30')).toBeInTheDocument() // prolongación nocturna
    expect(screen.getAllByText('Falta la salida').length).toBeGreaterThan(0)
    const boxes = screen.getAllByRole('checkbox', { name: /Seleccionar Carlos/ })
    expect(boxes[1]).toBeDisabled()

    await userEvent.click(boxes[0])
    await userEvent.click(screen.getByRole('button', { name: /Aprobar seleccionadas/ }))
    const post = fetchMock.mock.calls.find(([, init]) => init?.method === 'POST')!
    expect(post[0]).toBe('/api/v1/timeclock/workdays/approve/')
    expect(JSON.parse(post[1]!.body as string)).toEqual({ ids: ['w1'] })
  })

  it('sin permiso de aprobación no muestra selección', async () => {
    mockApi(['timeclock.view'])
    renderWithProviders(<WorkDaysPage />)
    await screen.findAllByText('Carlos Batista')
    expect(screen.queryByRole('checkbox', { name: /Seleccionar/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Calcular jornadas/ })).not.toBeInTheDocument()
  })
})
