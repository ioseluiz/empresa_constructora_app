import { zodResolver } from '@hookform/resolvers/zod'
import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { z } from 'zod'
import { ApiError } from '@/api/client'
import { Alert } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { FormField } from '@/components/ui/form-field'
import { Input } from '@/components/ui/input'
import { useAuth } from './use-auth'
import { AuthLayout } from './auth-layout'

const schema = z.object({
  email: z.email('Ingresa un correo válido.'),
  password: z.string().min(1, 'Ingresa tu contraseña.'),
})
type FormValues = z.infer<typeof schema>

export function LoginPage() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [error, setError] = useState<string | null>(null)
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({ resolver: zodResolver(schema) })

  const onSubmit = async ({ email, password }: FormValues) => {
    setError(null)
    try {
      await login(email, password)
      const from = (location.state as { from?: string } | null)?.from ?? '/'
      navigate(from, { replace: true })
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 429
          ? 'Demasiados intentos. Espera un minuto e inténtalo de nuevo.'
          : err instanceof ApiError
            ? err.message
            : 'No se pudo conectar con el servidor.',
      )
    }
  }

  return (
    <AuthLayout title="Iniciar sesión" subtitle="Ingresa con tu correo corporativo.">
      <form onSubmit={handleSubmit(onSubmit)} className="space-y-5" noValidate>
        {error && <Alert>{error}</Alert>}
        <FormField id="email" label="Correo electrónico" error={errors.email?.message}>
          <Input
            id="email"
            type="email"
            autoComplete="email"
            placeholder="nombre@empresa.com"
            aria-invalid={!!errors.email}
            {...register('email')}
          />
        </FormField>
        <FormField
          id="password"
          label="Contraseña"
          error={errors.password?.message}
          hint={
            <Link
              to="/recuperar-contrasena"
              className="text-primary text-xs font-medium hover:underline"
            >
              ¿Olvidaste tu contraseña?
            </Link>
          }
        >
          <Input
            id="password"
            type="password"
            autoComplete="current-password"
            aria-invalid={!!errors.password}
            {...register('password')}
          />
        </FormField>
        <Button type="submit" className="w-full" loading={isSubmitting}>
          Ingresar
        </Button>
      </form>
    </AuthLayout>
  )
}
