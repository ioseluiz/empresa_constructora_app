// Cliente HTTP mínimo. En el Sprint 2 se reemplaza por el cliente generado
// desde OpenAPI (orval) y se agrega el manejo de autenticación.
export class ApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

export async function apiGet<T>(path: string): Promise<T> {
  const response = await fetch(`/api/v1${path}`, {
    credentials: 'include',
    headers: { Accept: 'application/json' },
  })
  if (!response.ok) throw new ApiError(response.status, response.statusText)
  return (await response.json()) as T
}
