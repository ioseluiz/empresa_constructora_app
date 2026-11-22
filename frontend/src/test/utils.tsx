import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render } from '@testing-library/react'
import type { ReactElement } from 'react'
import { MemoryRouter } from 'react-router-dom'
import { vi } from 'vitest'
import type { User } from '@/features/auth/types'
import { AuthContext, type AuthContextValue } from '@/features/auth/use-auth'

export const testUser: User = {
  id: 'u1',
  email: 'ana@constructora.pa',
  first_name: 'Ana',
  last_name: 'Pérez',
  full_name: 'Ana Pérez',
  mfa_enabled: false,
  memberships: [
    {
      tenant_id: 't1',
      tenant_name: 'Constructora Istmo',
      tenant_slug: 'istmo',
      is_owner: true,
      require_mfa: false,
    },
  ],
}

export function renderWithProviders(ui: ReactElement, auth: Partial<AuthContextValue> = {}) {
  const value: AuthContextValue = {
    status: 'authenticated',
    user: testUser,
    currentTenant: testUser.memberships[0],
    login: vi.fn(),
    verifyMfa: vi.fn(),
    startSession: vi.fn(),
    refreshUser: vi.fn(),
    logout: vi.fn(),
    selectTenant: vi.fn(),
    ...auth,
  }
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return {
    auth: value,
    ...render(
      <QueryClientProvider client={client}>
        <AuthContext.Provider value={value}>
          <MemoryRouter>{ui}</MemoryRouter>
        </AuthContext.Provider>
      </QueryClientProvider>,
    ),
  }
}

export function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}
