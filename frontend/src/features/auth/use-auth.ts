import { createContext, useContext } from 'react'
import type { Membership, User } from './types'

export type AuthStatus = 'loading' | 'authenticated' | 'anonymous'

export interface AuthContextValue {
  status: AuthStatus
  user: User | null
  currentTenant: Membership | null
  /** Devuelve `{ mfaToken }` si la cuenta exige un segundo factor. */
  login: (email: string, password: string) => Promise<{ mfaToken?: string }>
  verifyMfa: (mfaToken: string, code: string) => Promise<void>
  /** Inicia sesión con una respuesta de login ya obtenida (p. ej. al aceptar una invitación). */
  startSession: (access: string, user: User) => void
  refreshUser: () => Promise<void>
  logout: () => Promise<void>
  selectTenant: (tenantId: string) => void
}

export const AuthContext = createContext<AuthContextValue | null>(null)

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth debe usarse dentro de <AuthProvider>')
  return ctx
}
