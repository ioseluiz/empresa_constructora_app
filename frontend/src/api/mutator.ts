import { apiFetch } from './client'

/** Punto de entrada que usa el código generado por orval: reutiliza token, empresa activa,
 * renovación automática y manejo de errores del cliente base. */
export const customFetch = <T>(url: string, options: RequestInit = {}): Promise<T> =>
  apiFetch<T>(url, options)

export type ErrorType<E> = import('./client').ApiError & { data?: E }
export type BodyType<B> = B
