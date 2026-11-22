import { zodResolver } from '@hookform/resolvers/zod'
import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { z } from 'zod'
import { ApiError } from '@/api/client'
import { Alert } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { FormField } from '@/components/ui/form-field'
import { Input } from '@/components/ui/input'
import { authApi } from './auth-api'
import { AuthLayout } from './auth-layout'

const schema = z
  .object({
    password: z.string().min(10, 'Debe tener al menos 10 caracteres.'),
    confirm: z.string(),
  })
  .refine((v) => v.password === v.confirm, {
    path: ['confirm'],
    message: 'Las contraseñas no coinciden.',
  })
type FormValues = z.infer<typeof schema>

export function ResetPasswordPage() {
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const uid = params.get('uid')
  const token = params.get('token')
  const [done, setDone] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({ resolver: zodResolver(schema) })

  const onSubmit = async ({ password }: FormValues) => {
    if (!uid || !token) return
    setError(null)
    try {
      await authApi.confirmPasswordReset(uid, token, password)
      setDone(true)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'No se pudo cambiar la contraseña.')
    }
  }

  return (
    <AuthLayout title="Nueva contraseña" subtitle="Elige una contraseña segura para tu cuenta.">
      {!uid || !token ? (
        <Alert>El enlace no es válido. Solicita uno nuevo.</Alert>
      ) : done ? (
        <div className="space-y-5">
          <Alert variant="success">Tu contraseña se actualizó correctamente.</Alert>
          <Button className="w-full" onClick={() => navigate('/login')}>
            Iniciar sesión
          </Button>
        </div>
      ) : (
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-5" noValidate>
          {error && <Alert>{error}</Alert>}
          <FormField id="password" label="Nueva contraseña" error={errors.password?.message}>
            <Input
              id="password"
              type="password"
              autoComplete="new-password"
              aria-invalid={!!errors.password}
              {...register('password')}
            />
          </FormField>
          <FormField id="confirm" label="Confirmar contraseña" error={errors.confirm?.message}>
            <Input
              id="confirm"
              type="password"
              autoComplete="new-password"
              aria-invalid={!!errors.confirm}
              {...register('confirm')}
            />
          </FormField>
          <Button type="submit" className="w-full" loading={isSubmitting}>
            Guardar contraseña
          </Button>
        </form>
      )}
      <Link to="/recuperar-contrasena" className="text-muted-foreground text-sm hover:underline">
        Solicitar un enlace nuevo
      </Link>
    </AuthLayout>
  )
}
