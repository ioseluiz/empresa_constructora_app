import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { DashboardPage } from './dashboard-page'

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <DashboardPage />
    </QueryClientProvider>,
  )
}

describe('DashboardPage', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('muestra la API operativa cuando el health check responde ok', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValue(
          new Response(JSON.stringify({ status: 'ok', database: 'ok' }), { status: 200 }),
        ),
    )
    renderPage()
    expect(await screen.findByText('API operativa')).toBeInTheDocument()
  })

  it('muestra error cuando la API no responde', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('', { status: 503 })))
    renderPage()
    expect(await screen.findByText('API no disponible')).toBeInTheDocument()
  })
})
