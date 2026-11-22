import { screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { jsonResponse, renderWithProviders } from '@/test/utils'
import { AppLayout } from './app-layout'

function mockAccess(body: unknown, status = 200) {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(body, status)))
}

describe('AppLayout', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('muestra solo las secciones de configuración permitidas', async () => {
    mockAccess({
      is_owner: false,
      permissions: ['audit.view'],
      roles: ['Auditor'],
      require_mfa: false,
    })
    renderWithProviders(<AppLayout />)
    expect(await screen.findByRole('link', { name: 'Auditoría' })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Usuarios' })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Roles' })).not.toBeInTheDocument()
  })

  it('bloquea el contenido si la empresa exige MFA y el usuario no lo tiene', async () => {
    mockAccess({ detail: 'Activa MFA', code: 'mfa_setup_required' }, 403)
    renderWithProviders(<AppLayout />)
    expect(await screen.findByText('Activa la verificación en dos pasos')).toBeInTheDocument()
  })
})
