import { zodResolver } from '@hookform/resolvers/zod'
import { ArrowLeft, MailCheck } from 'lucide-react'
import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { Link } from 'react-router-dom'
import { z } from 'zod'
import { Alert } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { FormField } from '@/components/ui/form-field'
import { Input } from '@/components/ui/input'
import { authApi } from './auth-api'
import { AuthLayout } from './auth-layout'

const schema = z.object({ email: z.email('Ingresa un correo válido.') })
type FormValues = z.infer<typeof schema>

export function ForgotPasswordPage() {
  const [sentTo, setSentTo] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({ resolver: zodResolver(schema) })

  const onSubmit = async ({ email }: FormValues) => {
    setError(null)
    try {
      await authApi.requestPasswordReset(email)
      setSentTo(email)
    } catch {
      setError('No se pudo enviar la solicitud. Inténtalo más tarde.')
    }
  }

  return (
    <AuthLayout
      title="Recuperar contraseña"
      subtitle="Te enviaremos un enlace para crear una nueva contraseña."
    >
      {sentTo ? (
        <Alert variant="success" className="flex gap-3">
          <MailCheck className="size-5 shrink-0" />
          <span>
            Si <strong>{sentTo}</strong> está registrado, recibirás un correo con las instrucciones
            en unos minutos.
          </span>
        </Alert>
      ) : (
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-5" noValidate>
          {error && <Alert>{error}</Alert>}
          <FormField id="email" label="Correo electrónico" error={errors.email?.message}>
            <Input
              id="email"
              type="email"
              autoComplete="email"
              aria-invalid={!!errors.email}
              {...register('email')}
            />
          </FormField>
          <Button type="submit" className="w-full" loading={isSubmitting}>
            Enviar enlace
          </Button>
        </form>
      )}
      <Link
        to="/login"
        className="text-muted-foreground hover:text-foreground inline-flex items-center gap-1.5 text-sm"
      >
        <ArrowLeft className="size-4" /> Volver a iniciar sesión
      </Link>
    </AuthLayout>
  )
}
