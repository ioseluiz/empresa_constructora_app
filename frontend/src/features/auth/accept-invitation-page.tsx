import { useState, type FormEvent } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { ApiError } from '@/api/client'
import {
  useAuthInvitationsAcceptCreate,
  useAuthInvitationsRetrieve,
} from '@/api/generated/auth/auth'
import { Alert } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { FormField } from '@/components/ui/form-field'
import { Input } from '@/components/ui/input'
import { LoadingBlock } from '@/components/ui/page'
import { AuthLayout } from './auth-layout'
import { useAuth } from './use-auth'

export function AcceptInvitationPage() {
  const [params] = useSearchParams()
  const token = params.get('token') ?? ''
  const navigate = useNavigate()
  const { startSession } = useAuth()
  const info = useAuthInvitationsRetrieve(token, { query: { enabled: !!token, retry: false } })
  const [form, setForm] = useState({ first_name: '', last_name: '', password: '', confirm: '' })
  const [error, setError] = useState<string | null>(null)
  const accept = useAuthInvitationsAcceptCreate({
    mutation: {
      onSuccess: ({ access, user }) => {
        startSession(access, user)
        navigate('/', { replace: true })
      },
      onError: (err) =>
        setError(err instanceof ApiError ? err.message : 'No se pudo aceptar la invitación.'),
    },
  })

  if (!token || info.isError) {
    return (
      <AuthLayout title="Invitación no válida">
        <Alert>
          El enlace no es válido o ya expiró. Pide al administrador que te invite de nuevo.
        </Alert>
      </AuthLayout>
    )
  }
  if (!info.data) return <LoadingBlock />

  const existing = info.data.user_exists
  const submit = (e: FormEvent) => {
    e.preventDefault()
    setError(null)
    if (!existing && form.password !== form.confirm) {
      setError('Las contraseñas no coinciden.')
      return
    }
    accept.mutate({
      token,
      data: existing
        ? { password: form.password }
        : { first_name: form.first_name, last_name: form.last_name, password: form.password },
    })
  }
  const bind = (key: keyof typeof form) => ({
    id: key,
    value: form[key],
    onChange: (e: React.ChangeEvent<HTMLInputElement>) =>
      setForm({ ...form, [key]: e.target.value }),
  })

  return (
    <AuthLayout
      title={`Únete a ${info.data.tenant_name}`}
      subtitle={
        existing
          ? `Ya tienes una cuenta con ${info.data.email}. Confirma tu contraseña para unirte.`
          : `Crea tu cuenta para ${info.data.email}.`
      }
    >
      <form onSubmit={submit} className="space-y-5">
        {error && <Alert>{error}</Alert>}
        {!existing && (
          <div className="grid gap-4 sm:grid-cols-2">
            <FormField id="first_name" label="Nombre">
              <Input required autoComplete="given-name" {...bind('first_name')} />
            </FormField>
            <FormField id="last_name" label="Apellido">
              <Input required autoComplete="family-name" {...bind('last_name')} />
            </FormField>
          </div>
        )}
        <FormField id="password" label={existing ? 'Contraseña' : 'Crea una contraseña'}>
          <Input
            type="password"
            required
            minLength={existing ? undefined : 10}
            autoComplete={existing ? 'current-password' : 'new-password'}
            {...bind('password')}
          />
        </FormField>
        {!existing && (
          <FormField id="confirm" label="Confirmar contraseña">
            <Input type="password" required autoComplete="new-password" {...bind('confirm')} />
          </FormField>
        )}
        <Button type="submit" className="w-full" loading={accept.isPending}>
          {existing ? 'Unirme' : 'Crear cuenta y unirme'}
        </Button>
      </form>
    </AuthLayout>
  )
}
