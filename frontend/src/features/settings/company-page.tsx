import { useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { ApiError } from '@/api/client'
import {
  getTenantCurrentRetrieveQueryKey,
  useTenantCurrentPartialUpdate,
  useTenantCurrentRetrieve,
} from '@/api/generated/empresa/empresa'
import type { Tenant } from '@/api/generated/model'
import { Alert } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Switch } from '@/components/ui/checkbox'
import { FormField } from '@/components/ui/form-field'
import { Input } from '@/components/ui/input'
import { LoadingBlock, PageHeader } from '@/components/ui/page'

function CompanyForm({ tenant }: { tenant: Tenant }) {
  const queryClient = useQueryClient()
  const [form, setForm] = useState({
    name: tenant.name,
    legal_name: tenant.legal_name ?? '',
    ruc: tenant.ruc ?? '',
    dv: tenant.dv ?? '',
    require_mfa: tenant.require_mfa ?? false,
  })
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null)
  const update = useTenantCurrentPartialUpdate({
    mutation: {
      onSuccess: (data) => {
        queryClient.setQueryData(getTenantCurrentRetrieveQueryKey(), data)
        setMessage({ ok: true, text: 'Cambios guardados.' })
      },
      onError: (err) =>
        setMessage({
          ok: false,
          text: err instanceof ApiError ? err.message : 'No se pudo guardar.',
        }),
    },
  })
  const submit = (e: FormEvent) => {
    e.preventDefault()
    setMessage(null)
    update.mutate({ data: form })
  }
  const field = (key: 'name' | 'legal_name' | 'ruc' | 'dv') => ({
    id: key,
    value: form[key],
    onChange: (e: React.ChangeEvent<HTMLInputElement>) =>
      setForm({ ...form, [key]: e.target.value }),
  })

  return (
    <form onSubmit={submit} className="space-y-6">
      {message && <Alert variant={message.ok ? 'success' : 'danger'}>{message.text}</Alert>}
      <Card className="space-y-5 p-6">
        <h2 className="font-semibold">Datos generales</h2>
        <div className="grid gap-5 sm:grid-cols-2">
          <FormField id="name" label="Nombre comercial">
            <Input required {...field('name')} />
          </FormField>
          <FormField id="legal_name" label="Razón social">
            <Input {...field('legal_name')} />
          </FormField>
          <FormField id="ruc" label="RUC">
            <Input {...field('ruc')} placeholder="155-123-2026" />
          </FormField>
          <FormField id="dv" label="DV">
            <Input {...field('dv')} maxLength={2} className="max-w-24" />
          </FormField>
        </div>
        <p className="text-muted-foreground text-xs">
          País: Panamá · Moneda: {tenant.currency} · Zona horaria: {tenant.timezone}
        </p>
      </Card>
      <Card className="flex items-start justify-between gap-6 p-6">
        <div className="space-y-1">
          <h2 className="font-semibold">Exigir verificación en dos pasos</h2>
          <p className="text-muted-foreground text-sm">
            Los usuarios sin verificación en dos pasos no podrán ver datos de la empresa hasta
            activarla en su cuenta. Recomendado: la planilla contiene datos sensibles.
          </p>
        </div>
        <Switch
          checked={form.require_mfa}
          onCheckedChange={(v) => setForm({ ...form, require_mfa: v })}
          aria-label="Exigir verificación en dos pasos"
        />
      </Card>
      <div className="flex justify-end">
        <Button type="submit" loading={update.isPending}>
          Guardar cambios
        </Button>
      </div>
    </form>
  )
}

export function CompanyPage() {
  const tenant = useTenantCurrentRetrieve()
  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <PageHeader title="Empresa" description="Datos legales y políticas de seguridad." />
      {tenant.data ? <CompanyForm key={tenant.data.id} tenant={tenant.data} /> : <LoadingBlock />}
    </div>
  )
}
