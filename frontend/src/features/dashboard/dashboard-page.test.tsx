import { screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { jsonResponse, renderWithProviders } from '@/test/utils'
import { DashboardPage } from './dashboard-page'

function mockApi(healthStatus: number) {
  vi.stubGlobal(
    'fetch',
    vi.fn((url: string) =>
      Promise.resolve(
        url.includes('/health/')
          ? jsonResponse({ status: 'ok', database: 'ok' }, healthStatus)
          : jsonResponse({
              id: 't1',
              name: 'Istmo',
              legal_name: 'Constructora Istmo S.A.',
              ruc: '155-1',
              dv: '45',
            }),
      ),
    ),
  )
}

describe('DashboardPage', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('saluda al usuario y muestra los datos de la empresa', async () => {
    mockApi(200)
    renderWithProviders(<DashboardPage />)
    expect(screen.getByText('Hola, Ana')).toBeInTheDocument()
    expect(await screen.findByText('Constructora Istmo S.A.')).toBeInTheDocument()
    expect(screen.getByText('RUC 155-1 DV 45')).toBeInTheDocument()
    expect(await screen.findByText('API operativa')).toBeInTheDocument()
  })

  it('muestra error cuando la API no responde', async () => {
    mockApi(503)
    renderWithProviders(<DashboardPage />)
    expect(await screen.findByText('API no disponible')).toBeInTheDocument()
  })
})
