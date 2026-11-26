import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Navigate, Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { jsonResponse, renderWithProviders } from '@/test/utils'
import { RunPage } from './run-page'

const run = {
  id: 'r1',
  number: 3,
  run_type: 'regular',
  frequency: 'weekly',
  frequency_display: 'Semanal',
  scope: 'project',
  scope_display: 'Proyecto',
  project: 'p1',
  project_code: 'P-001',
  period_start: '2026-11-16',
  period_end: '2026-11-22',
  pay_date: '2026-11-27',
  status: 'calculated',
  status_display: 'Calculada',
  employee_count: 1,
  gross: '89.02',
  deductions: '9.79',
  net: '79.23',
  employer_contributions: '17.29',
  provisions: '17.22',
  notes: '',
  parameters: {},
  error_count: 0,
  warning_count: 0,
}
const line = {
  id: 'l1',
  employee: 'e1',
  employee_code: 'E-0001',
  employee_name: 'Carlos Batista',
  employee_id_number: '8-123-4567',
  pay_basis: 'hourly',
  gross: '89.02',
  deductions: '9.79',
  net: '79.23',
  employer_contributions: '17.29',
  provisions: '17.22',
  warnings: [],
  explanation: [],
  error: '',
  items: [
    {
      id: 'i1',
      code: 'HORAS_ORD',
      name: 'Horas ordinarias',
      kind: 'earning',
      quantity: '7.03',
      rate: '5.1',
      amount: '35.85',
      cost_center_code: 'P-001',
      detail: '',
    },
  ],
}

describe('RunPage', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('muestra la planilla calculada y pide confirmación antes de aprobar', async () => {
    const fetchMock = vi.fn((url: string, init?: RequestInit) => {
      if (url.includes('/iam/me/'))
        return Promise.resolve(
          jsonResponse({
            permissions: ['payroll.view', 'payroll.calculate', 'payroll.approve'],
            roles: [],
          }),
        )
      if (init?.method === 'POST')
        return Promise.resolve(
          jsonResponse({ ...run, status: 'approved', status_display: 'Aprobada' }),
        )
      if (url.includes('/lines/'))
        return Promise.resolve(
          jsonResponse({ count: 1, next: null, previous: null, results: [line] }),
        )
      if (url.includes('/summary/'))
        return Promise.resolve(
          jsonResponse({
            runs: 1,
            employees: 1,
            totals: {},
            by_cost_center: [
              {
                cost_center: 'P-001',
                name: 'Torre',
                earning: '89.02',
                employer: '17.29',
                provision: '17.22',
                deduction: '9.79',
                total_cost: '123.53',
              },
            ],
            by_concept: [],
          }),
        )
      return Promise.resolve(jsonResponse(run))
    })
    vi.stubGlobal('fetch', fetchMock)
    renderWithProviders(
      <Routes>
        <Route path="/" element={<Navigate to="/planilla/corridas/r1" />} />
        <Route path="/planilla/corridas/:id" element={<RunPage />} />
      </Routes>,
    )
    expect(await screen.findByText('Carlos Batista')).toBeInTheDocument()
    expect(screen.getAllByText('B/. 79.23').length).toBeGreaterThan(0)
    expect(screen.getAllByText('B/. 123.53')).toHaveLength(2) // centro de costo y empleado

    await userEvent.click(screen.getByText('Carlos Batista'))
    expect(screen.getByText('Horas ordinarias')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: /^Aprobar$/ }))
    expect(screen.getByText(/ya no podrá modificarse/)).toBeInTheDocument()
    expect(fetchMock.mock.calls.some(([, init]) => init?.method === 'POST')).toBe(false)
    await userEvent.click(screen.getAllByRole('button', { name: /^Aprobar$/ }).at(-1)!)
    const post = fetchMock.mock.calls.find(([, init]) => init?.method === 'POST')!
    expect(post[0]).toBe('/api/v1/payroll/runs/r1/approve/')
  })
})
