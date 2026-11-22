import { useState } from 'react'
import { ApiError } from '@/api/client'

/** Manejo uniforme de errores de formularios: errores por campo + mensaje general. */
export function useFormErrors() {
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [error, setError] = useState<string | null>(null)
  const reset = () => {
    setErrors({})
    setError(null)
  }
  const handle = (err: unknown) => {
    if (err instanceof ApiError && err.data && typeof err.data === 'object') {
      const fe = Object.fromEntries(
        Object.entries(err.data as Record<string, unknown>)
          .filter(([k, v]) => Array.isArray(v) && k !== 'non_field_errors')
          .map(([k, v]) => [k, String((v as string[])[0])]),
      )
      setErrors(fe)
      setError(Object.keys(fe).length ? null : err.message)
      return
    }
    setError(err instanceof ApiError ? err.message : 'No se pudo completar la acción.')
  }
  return { errors, error, setError, reset, handle }
}
