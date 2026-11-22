/**
 * Cliente HTTP de la API.
 *
 * - El access token vive solo en memoria (nunca en localStorage).
 * - El refresh token es una cookie httpOnly que el navegador envía a /api/v1/auth/.
 * - Ante un 401 se intenta renovar el access token una sola vez y se repite la petición.
 * - Cada petición lleva el encabezado X-Tenant-ID con la empresa activa.
 */

const API_BASE = '/api/v1'
const TENANT_STORAGE_KEY = 'tenantId'

export class ApiError extends Error {
  readonly status: number
  readonly data: unknown

  constructor(status: number, message: string, data?: unknown) {
    super(message)
    this.status = status
    this.data = data
  }
}

let accessToken: string | null = null
let refreshPromise: Promise<string | null> | null = null
let onSessionExpired: (() => void) | null = null

export function setAccessToken(token: string | null) {
  accessToken = token
}

export function setSessionExpiredHandler(handler: (() => void) | null) {
  onSessionExpired = handler
}

export function getStoredTenantId(): string | null {
  try {
    return localStorage.getItem(TENANT_STORAGE_KEY)
  } catch {
    return null
  }
}

export function storeTenantId(id: string | null) {
  try {
    if (id) localStorage.setItem(TENANT_STORAGE_KEY, id)
    else localStorage.removeItem(TENANT_STORAGE_KEY)
  } catch {
    /* almacenamiento no disponible */
  }
}

/** Renueva el access token usando la cookie. Comparte una sola petición en vuelo. */
export function refreshAccessToken(): Promise<string | null> {
  refreshPromise ??= fetch(`${API_BASE}/auth/refresh/`, {
    method: 'POST',
    credentials: 'include',
  })
    .then(async (res) => {
      if (!res.ok) return null
      const { access } = (await res.json()) as { access: string }
      return access
    })
    .catch(() => null)
    .then((token) => {
      setAccessToken(token)
      return token
    })
    .finally(() => {
      refreshPromise = null
    })
  return refreshPromise
}

interface RequestOptions {
  body?: unknown
  /** Peticiones públicas (login, recuperación): sin token ni reintento. */
  anonymous?: boolean
}

function firstErrorMessage(data: unknown): string | undefined {
  if (!data || typeof data !== 'object') return undefined
  const record = data as Record<string, unknown>
  if (typeof record.detail === 'string') return record.detail
  for (const value of Object.values(record)) {
    if (Array.isArray(value) && typeof value[0] === 'string') return value[0]
  }
  return undefined
}

async function send(method: string, path: string, options: RequestOptions): Promise<Response> {
  const headers: Record<string, string> = { Accept: 'application/json' }
  if (options.body !== undefined) headers['Content-Type'] = 'application/json'
  if (!options.anonymous && accessToken) headers.Authorization = `Bearer ${accessToken}`
  const tenantId = getStoredTenantId()
  if (tenantId) headers['X-Tenant-ID'] = tenantId
  return fetch(`${API_BASE}${path}`, {
    method,
    headers,
    credentials: 'include',
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
  })
}

export async function apiRequest<T>(
  method: string,
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  let response = await send(method, path, options)

  if (response.status === 401 && !options.anonymous) {
    const token = await refreshAccessToken()
    if (token) {
      response = await send(method, path, options)
    } else {
      onSessionExpired?.()
    }
  }

  if (!response.ok) {
    const data: unknown = await response.json().catch(() => undefined)
    throw new ApiError(
      response.status,
      firstErrorMessage(data) ?? 'Ocurrió un error inesperado.',
      data,
    )
  }
  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

export const api = {
  get: <T>(path: string, options?: RequestOptions) => apiRequest<T>('GET', path, options),
  post: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    apiRequest<T>('POST', path, { ...options, body }),
  patch: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    apiRequest<T>('PATCH', path, { ...options, body }),
}

/** @deprecated usar `api.get` */
export const apiGet = <T>(path: string) => api.get<T>(path)
