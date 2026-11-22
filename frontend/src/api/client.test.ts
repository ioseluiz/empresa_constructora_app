import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { jsonResponse } from '@/test/utils'
import {
  api,
  ApiError,
  errorCode,
  setAccessToken,
  setSessionExpiredHandler,
  storeTenantId,
} from './client'

describe('api client', () => {
  beforeEach(() => {
    setAccessToken('viejo')
    storeTenantId('t1')
  })
  afterEach(() => {
    vi.unstubAllGlobals()
    setSessionExpiredHandler(null)
    storeTenantId(null)
  })

  it('envía token y empresa activa', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ ok: true }))
    vi.stubGlobal('fetch', fetchMock)
    await api.get('/tenant/current/')
    const headers = fetchMock.mock.calls[0][1].headers as Headers
    expect(headers.get('Authorization')).toBe('Bearer viejo')
    expect(headers.get('X-Tenant-ID')).toBe('t1')
  })

  it('renueva el token ante un 401 y repite la petición', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ detail: 'expirado' }, 401))
      .mockResolvedValueOnce(jsonResponse({ access: 'nuevo' }))
      .mockResolvedValueOnce(jsonResponse({ name: 'Istmo' }))
    vi.stubGlobal('fetch', fetchMock)

    await expect(api.get('/tenant/current/')).resolves.toEqual({ name: 'Istmo' })
    expect(fetchMock.mock.calls[1][0]).toBe('/api/v1/auth/refresh/')
    expect((fetchMock.mock.calls[2][1].headers as Headers).get('Authorization')).toBe(
      'Bearer nuevo',
    )
  })

  it('notifica sesión expirada si la renovación falla', async () => {
    const expired = vi.fn()
    setSessionExpiredHandler(expired)
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValueOnce(jsonResponse({ detail: 'expirado' }, 401))
        .mockResolvedValueOnce(jsonResponse({ detail: 'sin sesión' }, 401)),
    )
    await expect(api.get('/auth/me/')).rejects.toBeInstanceOf(ApiError)
    expect(expired).toHaveBeenCalledOnce()
  })

  it('acepta rutas completas del código generado y expone el código de error', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(jsonResponse({ detail: 'Activa MFA', code: 'mfa_setup_required' }, 403))
    vi.stubGlobal('fetch', fetchMock)
    const error = await api.get('/api/v1/iam/me/').catch((e: unknown) => e)
    expect(fetchMock.mock.calls[0][0]).toBe('/api/v1/iam/me/')
    expect(errorCode(error)).toBe('mfa_setup_required')
  })

  it('extrae el primer mensaje de validación', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(jsonResponse({ new_password: ['Muy corta.'] }, 400)),
    )
    await expect(api.post('/auth/password/change/', {})).rejects.toThrow('Muy corta.')
  })
})
