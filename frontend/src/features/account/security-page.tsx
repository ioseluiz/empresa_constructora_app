import { useQueryClient } from '@tanstack/react-query'
import { ShieldCheck, ShieldOff, Smartphone } from 'lucide-react'
import { useEffect, useRef, useState, type FormEvent } from 'react'
import { ApiError } from '@/api/client'
import { useAuthPasswordChangeCreate } from '@/api/generated/auth/auth'
import {
  getAuthMfaRetrieveQueryKey,
  useAuthMfaDisableCreate,
  useAuthMfaEnableCreate,
  useAuthMfaRetrieve,
  useAuthMfaSetupCreate,
} from '@/api/generated/mfa/mfa'
import type { MFASetup } from '@/api/generated/model'
import { Alert } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Dialog } from '@/components/ui/dialog'
import { FormField } from '@/components/ui/form-field'
import { Input } from '@/components/ui/input'
import { PageHeader } from '@/components/ui/page'
import { useAuth } from '@/features/auth/use-auth'
import { RecoveryCodes } from './recovery-codes'

const msg = (err: unknown, fallback: string) => (err instanceof ApiError ? err.message : fallback)

function PasswordCard() {
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [result, setResult] = useState<{ ok: boolean; text: string } | null>(null)
  const change = useAuthPasswordChangeCreate({
    mutation: {
      onSuccess: () => {
        setCurrent('')
        setNext('')
        setResult({ ok: true, text: 'Contraseña actualizada.' })
      },
      onError: (err) => setResult({ ok: false, text: msg(err, 'No se pudo cambiar.') }),
    },
  })
  const submit = (e: FormEvent) => {
    e.preventDefault()
    setResult(null)
    change.mutate({ data: { current_password: current, new_password: next } })
  }
  return (
    <Card className="p-6">
      <form onSubmit={submit} className="space-y-5">
        <h2 className="font-semibold">Contraseña</h2>
        {result && <Alert variant={result.ok ? 'success' : 'danger'}>{result.text}</Alert>}
        <div className="grid gap-5 sm:grid-cols-2">
          <FormField id="current-password" label="Contraseña actual">
            <Input
              id="current-password"
              type="password"
              autoComplete="current-password"
              required
              value={current}
              onChange={(e) => setCurrent(e.target.value)}
            />
          </FormField>
          <FormField id="new-password" label="Nueva contraseña">
            <Input
              id="new-password"
              type="password"
              autoComplete="new-password"
              minLength={10}
              required
              value={next}
              onChange={(e) => setNext(e.target.value)}
            />
          </FormField>
        </div>
        <div className="flex justify-end">
          <Button type="submit" loading={change.isPending}>
            Cambiar contraseña
          </Button>
        </div>
      </form>
    </Card>
  )
}

function EnableMfaDialog({ onClose, onEnabled }: { onClose: () => void; onEnabled: () => void }) {
  const [setup, setSetup] = useState<MFASetup | null>(null)
  const [code, setCode] = useState('')
  const [codes, setCodes] = useState<string[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const start = useAuthMfaSetupCreate({
    mutation: { onSuccess: setSetup, onError: (e) => setError(msg(e, 'No se pudo iniciar.')) },
  })
  const enable = useAuthMfaEnableCreate({
    mutation: {
      onSuccess: (data) => {
        setCodes(data.recovery_codes)
        onEnabled()
      },
      onError: (e) => setError(msg(e, 'Código inválido.')),
    },
  })
  const started = useRef(false)
  useEffect(() => {
    if (started.current) return
    started.current = true
    start.mutate()
  }, [start])

  return (
    <Dialog
      open
      onOpenChange={(o) => !o && onClose()}
      title={codes ? 'Códigos de recuperación' : 'Activar verificación en dos pasos'}
      description={
        codes ? undefined : 'Escanea el código con tu app de autenticación y escribe el código.'
      }
      footer={
        codes ? (
          <Button onClick={onClose}>Listo, los guardé</Button>
        ) : (
          <Button
            type="submit"
            form="mfa-enable"
            loading={enable.isPending}
            disabled={code.length !== 6}
          >
            Activar
          </Button>
        )
      }
    >
      {codes ? (
        <RecoveryCodes codes={codes} />
      ) : (
        <form
          id="mfa-enable"
          className="space-y-5"
          onSubmit={(e) => {
            e.preventDefault()
            setError(null)
            enable.mutate({ data: { code } })
          }}
        >
          {error && <Alert>{error}</Alert>}
          <ol className="text-muted-foreground list-decimal space-y-1 pl-5 text-sm">
            <li>Instala Google Authenticator, Microsoft Authenticator o similar.</li>
            <li>Escanea este código QR.</li>
            <li>Escribe el código de 6 dígitos que muestra la app.</li>
          </ol>
          {setup && (
            <div className="flex flex-col items-center gap-3">
              <div
                className="rounded-lg bg-white p-2"
                // SVG generado por nuestro backend (segno), no contenido de usuarios.
                dangerouslySetInnerHTML={{ __html: setup.qr_svg }}
              />
              <details className="text-muted-foreground text-center text-xs">
                <summary className="cursor-pointer">¿No puedes escanear? Ingresa la clave</summary>
                <code className="text-foreground mt-2 block font-mono text-sm tracking-wider break-all">
                  {setup.secret}
                </code>
              </details>
            </div>
          )}
          <FormField id="mfa-code" label="Código de verificación">
            <Input
              id="mfa-code"
              inputMode="numeric"
              autoComplete="one-time-code"
              maxLength={6}
              value={code}
              onChange={(e) => setCode(e.target.value.replace(/\D/g, ''))}
              className="text-center font-mono text-lg tracking-[0.4em]"
            />
          </FormField>
        </form>
      )}
    </Dialog>
  )
}

function DisableMfaDialog({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const [password, setPassword] = useState('')
  const [code, setCode] = useState('')
  const [error, setError] = useState<string | null>(null)
  const disable = useAuthMfaDisableCreate({
    mutation: {
      onSuccess: () => {
        onDone()
        onClose()
      },
      onError: (e) => setError(msg(e, 'No se pudo desactivar.')),
    },
  })
  return (
    <Dialog
      open
      onOpenChange={(o) => !o && onClose()}
      title="Desactivar verificación en dos pasos"
      description="Tu cuenta quedará protegida solo por la contraseña."
      footer={
        <Button type="submit" form="mfa-disable" loading={disable.isPending}>
          Desactivar
        </Button>
      }
    >
      <form
        id="mfa-disable"
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault()
          setError(null)
          disable.mutate({ data: { password, code } })
        }}
      >
        {error && <Alert>{error}</Alert>}
        <FormField id="disable-password" label="Contraseña">
          <Input
            id="disable-password"
            type="password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </FormField>
        <FormField id="disable-code" label="Código de la app o de recuperación">
          <Input
            id="disable-code"
            required
            value={code}
            onChange={(e) => setCode(e.target.value)}
          />
        </FormField>
      </form>
    </Dialog>
  )
}

function MfaCard() {
  const queryClient = useQueryClient()
  const { refreshUser } = useAuth()
  const status = useAuthMfaRetrieve()
  const [dialog, setDialog] = useState<'enable' | 'disable' | null>(null)
  const changed = () => {
    void queryClient.invalidateQueries({ queryKey: getAuthMfaRetrieveQueryKey() })
    void refreshUser()
  }
  const enabled = status.data?.enabled

  return (
    <Card className="p-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex gap-4">
          <span className="bg-muted flex size-10 shrink-0 items-center justify-center rounded-full">
            <Smartphone className="text-muted-foreground size-5" />
          </span>
          <div className="space-y-1">
            <h2 className="flex items-center gap-2 font-semibold">
              Verificación en dos pasos
              {enabled ? (
                <Badge variant="success">
                  <ShieldCheck className="size-3" /> Activa
                </Badge>
              ) : (
                <Badge>
                  <ShieldOff className="size-3" /> Inactiva
                </Badge>
              )}
            </h2>
            <p className="text-muted-foreground max-w-lg text-sm">
              Además de la contraseña, pide un código de tu teléfono al iniciar sesión.
              {enabled &&
                ` Te quedan ${status.data?.recovery_codes_remaining} códigos de recuperación.`}
            </p>
          </div>
        </div>
        {status.data &&
          (enabled ? (
            <Button variant="outline" onClick={() => setDialog('disable')}>
              Desactivar
            </Button>
          ) : (
            <Button onClick={() => setDialog('enable')}>Activar</Button>
          ))}
      </div>
      {dialog === 'enable' && (
        <EnableMfaDialog onClose={() => setDialog(null)} onEnabled={changed} />
      )}
      {dialog === 'disable' && (
        <DisableMfaDialog onClose={() => setDialog(null)} onDone={changed} />
      )}
    </Card>
  )
}

export function SecurityPage() {
  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <PageHeader
        title="Seguridad de la cuenta"
        description="Contraseña y verificación en dos pasos."
      />
      <MfaCard />
      <PasswordCard />
    </div>
  )
}
