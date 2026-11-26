import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { jsonResponse, renderWithProviders } from '@/test/utils'
import { VacationsPage } from './vacations-page'

const vacation = {
  id: 'v1',
  employee: 'e1',
  employee_code: 'E-0001',
  employee_name: 'Carlos Batista',
  start_date: '2026-12-07',
  end_date: '2026-12-16',
  days: 10,
  payment_mode: 'payroll',
  payment_mode_display: 'En la planilla regular',
  status: 'requested',
  status_display: 'Solicitada',
  notes: '',
  reject_reason: '',
  is_paid: false,
  paid_amount: null,
  paid_run_number: null,
}

describe('VacationsPage', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('lista solicitudes pendientes y aprueba con confirmación', async () => {
    const fetchMock = vi.fn((url: string, init?: RequestInit) => {
      if (url.includes('/iam/me/'))
        return Promise.resolve(
          jsonResponse({ permissions: ['leave.view', 'leave.manage', 'leave.approve'], roles: [] }),
        )
      if (init?.method === 'POST')
        return Promise.resolve(jsonResponse({ ...vacation, status: 'approved' }))
      return Promise.resolve(
        jsonResponse({ count: 1, next: null, previous: null, results: [vacation] }),
      )
    })
    vi.stubGlobal('fetch', fetchMock)
    renderWithProviders(<VacationsPage />)
    expect(await screen.findByText('Carlos Batista')).toBeInTheDocument()
    expect(fetchMock.mock.calls.find(([u]) => u.includes('/leave/vacations/'))![0]).toContain(
      'status=requested',
    )
    await userEvent.click(screen.getByRole('button', { name: /Aprobar/ }))
    expect(screen.getByText(/10 días, del/)).toBeInTheDocument()
    await userEvent.click(screen.getAllByRole('button', { name: /^Aprobar$/ }).at(-1)!)
    const post = fetchMock.mock.calls.find(([, init]) => init?.method === 'POST')!
    expect(post[0]).toBe('/api/v1/leave/vacations/v1/approve/')
  })

  it('calcula la fecha de fin a partir de los días', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn((url: string) =>
        Promise.resolve(
          url.includes('/iam/me/')
            ? jsonResponse({ permissions: ['leave.view', 'leave.manage'], roles: [] })
            : jsonResponse({ count: 0, next: null, previous: null, results: [] }),
        ),
      ),
    )
    renderWithProviders(<VacationsPage />)
    await userEvent.click(await screen.findByRole('button', { name: /Nueva solicitud/ }))
    const start = screen.getByLabelText('Desde')
    await userEvent.clear(start)
    await userEvent.type(start, '2026-12-07')
    const days = screen.getByLabelText('Días')
    await userEvent.clear(days)
    await userEvent.type(days, '10')
    expect(screen.getByLabelText('Hasta')).toHaveValue('2026-12-16')
  })
})
