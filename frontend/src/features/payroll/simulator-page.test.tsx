import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { jsonResponse, renderWithProviders } from '@/test/utils'
import { SimulatorPage } from './simulator-page'

const result = {
  lines: [
    {
      code: 'HORAS_ORD',
      name: 'Horas ordinarias',
      kind: 'earning',
      amount: '182.00',
      quantity: '40.00',
      rate: '4.550000',
      cost_center: 'P-001',
      detail: 'tarifa 4.55 × 1',
    },
    {
      code: 'CSS',
      name: 'Seguro Social',
      kind: 'deduction',
      amount: '17.75',
      quantity: null,
      rate: '0.097500',
      cost_center: null,
      detail: 'base 182.00',
    },
    {
      code: 'CSS_PATRONAL',
      name: 'Seguro Social patronal',
      kind: 'employer',
      amount: '22.30',
      quantity: null,
      rate: '0.122500',
      cost_center: 'P-001',
      detail: 'base 182.00',
    },
  ],
  gross: '182.00',
  deductions: '17.75',
  net: '164.25',
  employer_cost: '204.30',
  warnings: ['1 jornada(s) del período sin aprobar: no se incluyen.'],
  explanation: [],
  parameters: { css_employee_rate: '0.097500 desde 2020-01-01' },
}

describe('SimulatorPage', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('calcula y muestra totales, líneas con tasas y advertencias', async () => {
    const fetchMock = vi.fn((url: string, init?: RequestInit) => {
      if (url.includes('/iam/me/'))
        return Promise.resolve(
          jsonResponse({ permissions: ['payroll.view', 'payroll.calculate'], roles: [] }),
        )
      if (url.includes('/hr/employees/'))
        return Promise.resolve(
          jsonResponse({
            count: 1,
            next: null,
            previous: null,
            results: [{ id: 'e1', code: 'E-0001', full_name: 'Carlos Batista' }],
          }),
        )
      if (init?.method === 'POST') return Promise.resolve(jsonResponse(result))
      return Promise.resolve(jsonResponse({}))
    })
    vi.stubGlobal('fetch', fetchMock)
    renderWithProviders(<SimulatorPage />)
    await userEvent.selectOptions(await screen.findByLabelText('Empleado'), 'e1')
    await userEvent.click(screen.getByRole('button', { name: /Calcular/ }))
    expect(await screen.findByText('Neto a pagar')).toBeInTheDocument()
    expect(screen.getByText('B/. 164.25')).toBeInTheDocument()
    expect(screen.getByText('9.75 %')).toBeInTheDocument()
    expect(screen.getByText(/sin aprobar/)).toBeInTheDocument()
    const post = fetchMock.mock.calls.find(([, init]) => init?.method === 'POST')!
    expect(post[0]).toBe('/api/v1/payroll/preview/')
    expect(JSON.parse(post[1]!.body as string).employee).toBe('e1')
  })

  it('sin permiso de cálculo muestra el aviso', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() =>
        Promise.resolve(
          jsonResponse({ permissions: ['payroll.view'], roles: [], count: 0, results: [] }),
        ),
      ),
    )
    renderWithProviders(<SimulatorPage />)
    expect(await screen.findByText(/Necesitas el permiso para calcular/)).toBeInTheDocument()
  })
})
