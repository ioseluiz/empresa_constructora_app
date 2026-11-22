import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { jsonResponse, renderWithProviders } from '@/test/utils'
import { HolidaysPage } from './holidays-page'

describe('HolidaysPage', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('lista los feriados del año con su día de la semana y permite generarlos', async () => {
    const fetchMock = vi.fn((_url: string, init?: RequestInit) =>
      Promise.resolve(
        init?.method === 'POST'
          ? jsonResponse([], 201)
          : jsonResponse([
              {
                id: 'h1',
                date: '2026-11-28',
                name: 'Independencia de Panamá de España',
                kind: 'national',
                kind_display: 'Fiesta nacional',
                is_paid_rest: true,
              },
            ]),
      ),
    )
    vi.stubGlobal('fetch', fetchMock)
    renderWithProviders(<HolidaysPage />)
    expect(await screen.findByText('Independencia de Panamá de España')).toBeInTheDocument()
    expect(screen.getByText('sábado')).toBeInTheDocument() // 28/11/2026, sin desfase de zona horaria
    expect(fetchMock.mock.calls[0][0]).toMatch(/year=\d{4}/)

    await userEvent.click(screen.getByRole('button', { name: /Cargar feriados/ }))
    const post = fetchMock.mock.calls.find(([, init]) => init?.method === 'POST')!
    expect(post[0]).toBe('/api/v1/org/holidays/generate/')
  })
})
