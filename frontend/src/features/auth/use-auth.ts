import { createContext, useContext } from 'react'
import type { Membership, User } from './types'

export type AuthStatus = 'loading' | 'authenticated' | 'anonymous'

export interface AuthContextValue {
  status: AuthStatus
  user: User | null
  currentTenant: Membership | null
  login: (email: string, password: string) => Promise<void>
  logout: () => Promise<void>
  selectTenant: (tenantId: string) => void
}

export const AuthContext = createContext<AuthContextValue | null>(null)

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth debe usarse dentro de <AuthProvider>')
  return ctx
}
