import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { jsonResponse, renderWithProviders } from '@/test/utils'
import { EmployeesPage } from './employees-page'

const employee = {
  id: 'e1',
  code: 'E-0001',
  first_name: 'Carlos',
  last_name: 'Batista',
  full_name: 'Carlos Batista',
  id_number: '8-123-4567',
  css_number: '123-4567',
  hire_date: '2026-01-05',
  status: 'active',
  status_display: 'Activo',
  current_projects: [{ id: 'p1', code: 'P-001', name: 'Torre' }],
  current_position: 'Albañil',
}

function mockApi(permissions: string[]) {
  const fetchMock = vi.fn((url: string, init?: RequestInit) => {
    if (url.includes('/iam/me/')) return Promise.resolve(jsonResponse({ permissions, roles: [] }))
    if (url.includes('/projects/'))
      return Promise.resolve(jsonResponse({ count: 0, next: null, previous: null, results: [] }))
    if (init?.method === 'POST') return Promise.resolve(jsonResponse({}, 400))
    return Promise.resolve(
      jsonResponse({ count: 1, next: null, previous: null, results: [employee] }),
    )
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

describe('EmployeesPage', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('lista empleados activos con su proyecto y puesto', async () => {
    const fetchMock = mockApi(['hr.employee.view'])
    renderWithProviders(<EmployeesPage />)
    expect(await screen.findByText('Carlos Batista')).toBeInTheDocument()
    expect(screen.getByText('P-001')).toBeInTheDocument()
    expect(screen.getByText('Albañil')).toBeInTheDocument()
    const listCall = fetchMock.mock.calls.find(([url]) => url.includes('/hr/employees/'))!
    expect(listCall[0]).toContain('status=active')
    expect(screen.queryByRole('button', { name: /Nuevo empleado/ })).not.toBeInTheDocument()
  })

  it('valida el formato de la cédula antes de enviar', async () => {
    const fetchMock = mockApi(['hr.employee.view', 'hr.employee.manage'])
    renderWithProviders(<EmployeesPage />)
    await userEvent.click(await screen.findByRole('button', { name: /Nuevo empleado/ }))
    await userEvent.type(screen.getByLabelText('Primer nombre'), 'Ana')
    await userEvent.type(screen.getByLabelText('Primer apellido'), 'Ruiz')
    await userEvent.type(screen.getByLabelText('Cédula'), '8123456')
    await userEvent.type(screen.getByLabelText('Fecha de ingreso'), '2026-02-01')
    await userEvent.click(screen.getByRole('button', { name: 'Crear empleado' }))
    expect(await screen.findByText(/Revisa la cédula/)).toBeInTheDocument()
    expect(fetchMock.mock.calls.some(([, init]) => init?.method === 'POST')).toBe(false)
  })
})
