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
    if (typeof value === 'string') return value
  }
  return undefined
}

function buildHeaders(init: RequestInit, anonymous: boolean): Headers {
  const headers = new Headers(init.headers)
  headers.set('Accept', 'application/json')
  // Con FormData el navegador fija el Content-Type multipart con su boundary.
  if (init.body !== undefined && !(init.body instanceof FormData) && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }
  if (!anonymous && accessToken) headers.set('Authorization', `Bearer ${accessToken}`)
  const tenantId = getStoredTenantId()
  if (tenantId) headers.set('X-Tenant-ID', tenantId)
  return headers
}

async function send(url: string, init: RequestInit, anonymous: boolean): Promise<Response> {
  const fullUrl = url.startsWith(API_BASE) ? url : `${API_BASE}${url}`
  const once = () =>
    fetch(fullUrl, { ...init, headers: buildHeaders(init, anonymous), credentials: 'include' })

  let response = await once()
  if (response.status === 401 && !anonymous) {
    const token = await refreshAccessToken()
    if (token) {
      response = await once()
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
  return response
}

/**
 * Petición a la API. `url` es la ruta completa (`/api/v1/...`) o relativa a `/api/v1`.
 * Lo usan tanto `api.*` como el código generado por orval (src/api/mutator.ts).
 */
export async function apiFetch<T>(
  url: string,
  init: RequestInit = {},
  { anonymous = false }: { anonymous?: boolean } = {},
): Promise<T> {
  const response = await send(url, init, anonymous)
  if (response.status === 204) return undefined as T
  const text = await response.text()
  return (text ? JSON.parse(text) : undefined) as T
}

/** Descarga un archivo autenticado (p. ej. documentos del expediente) y lo guarda. */
export async function downloadFile(url: string, filename: string): Promise<void> {
  const response = await send(url, {}, false)
  const href = URL.createObjectURL(await response.blob())
  const link = document.createElement('a')
  link.href = href
  link.download = filename
  link.click()
  setTimeout(() => URL.revokeObjectURL(href), 1000)
}

export function apiRequest<T>(
  method: string,
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  return apiFetch<T>(
    path,
    { method, body: options.body === undefined ? undefined : JSON.stringify(options.body) },
    { anonymous: options.anonymous },
  )
}

/** Código de error del backend (`{"detail": ..., "code": ...}`), si lo hay. */
export function errorCode(error: unknown): string | undefined {
  if (!(error instanceof ApiError) || !error.data || typeof error.data !== 'object')
    return undefined
  const code = (error.data as Record<string, unknown>).code
  return typeof code === 'string' ? code : undefined
}

export const api = {
  get: <T>(path: string, options?: RequestOptions) => apiRequest<T>('GET', path, options),
  post: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    apiRequest<T>('POST', path, { ...options, body }),
  patch: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    apiRequest<T>('PATCH', path, { ...options, body }),
  delete: <T>(path: string, options?: RequestOptions) => apiRequest<T>('DELETE', path, options),
}
