import { useQueryClient } from '@tanstack/react-query'
import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import {
  getStoredTenantId,
  refreshAccessToken,
  setAccessToken,
  setSessionExpiredHandler,
  storeTenantId,
} from '@/api/client'
import { authApi } from './auth-api'
import type { Membership, User } from './types'
import { AuthContext, type AuthStatus } from './use-auth'

function pickTenant(user: User): Membership | null {
  const stored = getStoredTenantId()
  return user.memberships.find((m) => m.tenant_id === stored) ?? user.memberships[0] ?? null
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient()
  const [status, setStatus] = useState<AuthStatus>('loading')
  const [user, setUser] = useState<User | null>(null)
  const [currentTenant, setCurrentTenant] = useState<Membership | null>(null)

  const applyUser = useCallback((next: User) => {
    const tenant = pickTenant(next)
    storeTenantId(tenant?.tenant_id ?? null)
    setUser(next)
    setCurrentTenant(tenant)
    setStatus('authenticated')
  }, [])

  const clearSession = useCallback(() => {
    setAccessToken(null)
    setUser(null)
    setCurrentTenant(null)
    setStatus('anonymous')
    queryClient.clear()
  }, [queryClient])

  // Al cargar la app intenta recuperar la sesión desde la cookie de refresh.
  useEffect(() => {
    let cancelled = false
    setSessionExpiredHandler(clearSession)
    refreshAccessToken()
      .then((token) => (token ? authApi.me() : null))
      .then((me) => {
        if (cancelled) return
        if (me) applyUser(me)
        else setStatus('anonymous')
      })
      .catch(() => !cancelled && setStatus('anonymous'))
    return () => {
      cancelled = true
      setSessionExpiredHandler(null)
    }
  }, [applyUser, clearSession])

  const login = useCallback(
    async (email: string, password: string) => {
      const { access, user: me } = await authApi.login(email, password)
      setAccessToken(access)
      applyUser(me)
    },
    [applyUser],
  )

  const logout = useCallback(async () => {
    try {
      await authApi.logout()
    } finally {
      clearSession()
    }
  }, [clearSession])

  const selectTenant = useCallback(
    (tenantId: string) => {
      const next = user?.memberships.find((m) => m.tenant_id === tenantId)
      if (!next) return
      storeTenantId(next.tenant_id)
      setCurrentTenant(next)
      queryClient.clear() // los datos en caché pertenecen a la empresa anterior
    },
    [user, queryClient],
  )

  const value = useMemo(
    () => ({ status, user, currentTenant, login, logout, selectTenant }),
    [status, user, currentTenant, login, logout, selectTenant],
  )
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
