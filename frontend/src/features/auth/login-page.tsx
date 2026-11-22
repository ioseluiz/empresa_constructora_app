import { zodResolver } from '@hookform/resolvers/zod'
import { ArrowLeft } from 'lucide-react'
import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { z } from 'zod'
import { ApiError } from '@/api/client'
import { Alert } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { FormField } from '@/components/ui/form-field'
import { Input } from '@/components/ui/input'
import { AuthLayout } from './auth-layout'
import { useAuth } from './use-auth'

const schema = z.object({
  email: z.email('Ingresa un correo válido.'),
  password: z.string().min(1, 'Ingresa tu contraseña.'),
})
type FormValues = z.infer<typeof schema>

function describeError(err: unknown) {
  if (err instanceof ApiError && err.status === 429)
    return 'Demasiados intentos. Espera un minuto e inténtalo de nuevo.'
  if (err instanceof ApiError) return err.message
  return 'No se pudo conectar con el servidor.'
}

function MfaStep({ mfaToken, onBack }: { mfaToken: string; onBack: () => void }) {
  const { verifyMfa } = useAuth()
  const [code, setCode] = useState('')
  const [useRecovery, setUseRecovery] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)
  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    setPending(true)
    try {
      await verifyMfa(mfaToken, code)
    } catch (err) {
      setError(describeError(err))
      setCode('')
    } finally {
      setPending(false)
    }
  }
  return (
    <AuthLayout
      title="Verificación en dos pasos"
      subtitle={
        useRecovery
          ? 'Escribe uno de tus códigos de recuperación.'
          : 'Escribe el código de 6 dígitos de tu app de autenticación.'
      }
    >
      <form onSubmit={(e) => void submit(e)} className="space-y-5">
        {error && <Alert>{error}</Alert>}
        <FormField id="mfa-code" label={useRecovery ? 'Código de recuperación' : 'Código'}>
          <Input
            id="mfa-code"
            autoFocus
            autoComplete="one-time-code"
            inputMode={useRecovery ? 'text' : 'numeric'}
            maxLength={useRecovery ? 9 : 6}
            value={code}
            onChange={(e) =>
              setCode(
                useRecovery ? e.target.value.toUpperCase() : e.target.value.replace(/\D/g, ''),
              )
            }
            className="text-center font-mono text-lg tracking-[0.3em]"
          />
        </FormField>
        <Button type="submit" className="w-full" loading={pending} disabled={!code}>
          Verificar
        </Button>
        <button
          type="button"
          className="text-primary w-full text-center text-sm hover:underline"
          onClick={() => {
            setUseRecovery(!useRecovery)
            setCode('')
          }}
        >
          {useRecovery
            ? 'Usar código de la app'
            : '¿Perdiste el teléfono? Usa un código de recuperación'}
        </button>
      </form>
      <button
        type="button"
        onClick={onBack}
        className="text-muted-foreground hover:text-foreground inline-flex items-center gap-1.5 text-sm"
      >
        <ArrowLeft className="size-4" /> Volver
      </button>
    </AuthLayout>
  )
}

export function LoginPage() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [error, setError] = useState<string | null>(null)
  const [mfaToken, setMfaToken] = useState<string | null>(null)
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({ resolver: zodResolver(schema) })

  const onSubmit = async ({ email, password }: FormValues) => {
    setError(null)
    try {
      const result = await login(email, password)
      if (result.mfaToken) {
        setMfaToken(result.mfaToken)
        return
      }
      const from = (location.state as { from?: string } | null)?.from ?? '/'
      navigate(from, { replace: true })
    } catch (err) {
      setError(describeError(err))
    }
  }

  if (mfaToken) return <MfaStep mfaToken={mfaToken} onBack={() => setMfaToken(null)} />

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
