import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { jsonResponse, renderWithProviders } from '@/test/utils'
import { PunchesPage } from './punches-page'

const punch = {
  id: 'p1',
  employee: 'e1',
  employee_code: 'E-0001',
  employee_name: 'Carlos Batista',
  timestamp: '2026-11-16T11:58:12Z', // 06:58:12 en Panamá (UTC-5)
  direction: 'in',
  direction_display: 'Entrada',
  source: 'device',
  source_display: 'Reloj',
  device_name: 'Reloj Torre',
  project_code: 'P-001',
  corrects: null,
  reason: '',
  is_void: false,
  void_reason: '',
}

function mockApi(permissions: string[]) {
  const fetchMock = vi.fn((url: string) => {
    if (url.includes('/iam/me/')) return Promise.resolve(jsonResponse({ permissions, roles: [] }))
    if (url.includes('/projects/') || url.includes('/hr/employees/'))
      return Promise.resolve(jsonResponse({ count: 0, next: null, previous: null, results: [] }))
    return Promise.resolve(jsonResponse({ count: 1, next: null, previous: null, results: [punch] }))
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

describe('PunchesPage', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('muestra la hora en zona de Panamá y filtra los últimos 7 días', async () => {
    const fetchMock = mockApi(['timeclock.view'])
    renderWithProviders(<PunchesPage />)
    expect(await screen.findByText('Carlos Batista')).toBeInTheDocument()
    expect(screen.getByText('06:58:12')).toBeInTheDocument()
    expect(screen.getByText('Reloj Torre')).toBeInTheDocument()
    const call = fetchMock.mock.calls.find(([url]) => url.includes('/timeclock/punches/'))!
    expect(call[0]).toMatch(/date_from=\d{4}-\d{2}-\d{2}/)
    expect(screen.queryByRole('button', { name: /Registro manual/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Corregir' })).not.toBeInTheDocument()
  })

  it('con permiso manual permite registrar y corregir', async () => {
    mockApi(['timeclock.view', 'timeclock.manual', 'hr.employee.view'])
    renderWithProviders(<PunchesPage />)
    await userEvent.click(await screen.findByRole('button', { name: 'Corregir' }))
    expect(screen.getByLabelText('Hora')).toHaveValue('06:58')
    expect(screen.getByLabelText('Fecha')).toHaveValue('2026-11-16')
  })
})
