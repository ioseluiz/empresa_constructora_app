import { useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { ApiError } from '@/api/client'
import type { Project, ProjectRequest } from '@/api/generated/model'
import {
  getProjectsListQueryKey,
  useProjectsCreate,
  useProjectsPartialUpdate,
} from '@/api/generated/proyectos/proyectos'
import { Alert } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Dialog } from '@/components/ui/dialog'
import { FormField } from '@/components/ui/form-field'
import { Input } from '@/components/ui/input'
import { Select } from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { PROJECT_STATUS, PROVINCES } from './constants'

type Form = {
  code: string
  name: string
  client: string
  province: string
  address: string
  status: string
  start_date: string
  estimated_end_date: string
  actual_end_date: string
  contract_amount: string
  description: string
}

function toForm(p?: Project): Form {
  return {
    code: p?.code ?? '',
    name: p?.name ?? '',
    client: p?.client ?? '',
    province: p?.province ?? '',
    address: p?.address ?? '',
    status: p?.status ?? 'planning',
    start_date: p?.start_date ?? '',
    estimated_end_date: p?.estimated_end_date ?? '',
    actual_end_date: p?.actual_end_date ?? '',
    contract_amount: p?.contract_amount ?? '',
    description: p?.description ?? '',
  }
}

/** Convierte cadenas vacías en null para fechas y montos opcionales. */
function toPayload(f: Form): ProjectRequest {
  const orNull = (v: string) => (v === '' ? null : v)
  return {
    ...f,
    province: f.province as ProjectRequest['province'],
    status: f.status as ProjectRequest['status'],
    start_date: orNull(f.start_date),
    estimated_end_date: orNull(f.estimated_end_date),
    actual_end_date: orNull(f.actual_end_date),
    contract_amount: orNull(f.contract_amount),
  }
}

function fieldErrors(err: unknown): Record<string, string> {
  if (!(err instanceof ApiError) || !err.data || typeof err.data !== 'object') return {}
  return Object.fromEntries(
    Object.entries(err.data as Record<string, unknown>)
      .filter(([, v]) => Array.isArray(v))
      .map(([k, v]) => [k, String((v as string[])[0])]),
  )
}

export function ProjectDialog({ project, onClose }: { project?: Project; onClose: () => void }) {
  const queryClient = useQueryClient()
  const [form, setForm] = useState<Form>(() => toForm(project))
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [error, setError] = useState<string | null>(null)
  const onSuccess = () => {
    void queryClient.invalidateQueries({ queryKey: getProjectsListQueryKey() })
    onClose()
  }
  const onError = (err: unknown) => {
    const fe = fieldErrors(err)
    setErrors(fe)
    setError(
      Object.keys(fe).length ? null : err instanceof ApiError ? err.message : 'Error al guardar.',
    )
  }
  const create = useProjectsCreate({ mutation: { onSuccess, onError } })
  const update = useProjectsPartialUpdate({ mutation: { onSuccess, onError } })

  const submit = (e: FormEvent) => {
    e.preventDefault()
    setErrors({})
    setError(null)
    const data = toPayload(form)
    if (project) update.mutate({ id: project.id, data })
    else create.mutate({ data })
  }
  const bind = (key: keyof Form) => ({
    id: `project-${key}`,
    value: form[key],
    'aria-invalid': !!errors[key],
    onChange: (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) =>
      setForm({ ...form, [key]: e.target.value }),
  })

  return (
    <Dialog
      open
      size="lg"
      onOpenChange={(o) => !o && onClose()}
      title={project ? `Editar ${project.code}` : 'Nuevo proyecto'}
      description="Cada proyecto tiene su propio centro de costo para imputar la planilla."
      footer={
        <>
          <Button variant="outline" onClick={onClose}>
            Cancelar
          </Button>
          <Button type="submit" form="project-form" loading={create.isPending || update.isPending}>
            Guardar
          </Button>
        </>
      }
    >
      <form id="project-form" onSubmit={submit} className="space-y-5">
        {error && <Alert>{error}</Alert>}
        <div className="grid gap-4 sm:grid-cols-[10rem_1fr]">
          <FormField id="project-code" label="Código" error={errors.code}>
            <Input required placeholder="P-001" {...bind('code')} />
          </FormField>
          <FormField id="project-name" label="Nombre" error={errors.name}>
            <Input required {...bind('name')} />
          </FormField>
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <FormField id="project-client" label="Cliente" error={errors.client}>
            <Input {...bind('client')} />
          </FormField>
          <FormField id="project-status" label="Estado" error={errors.status}>
            <Select className="w-full" {...bind('status')}>
              {Object.entries(PROJECT_STATUS).map(([v, { label }]) => (
                <option key={v} value={v}>
                  {label}
                </option>
              ))}
            </Select>
          </FormField>
          <FormField id="project-province" label="Provincia" error={errors.province}>
            <Select className="w-full" {...bind('province')}>
              <option value="">—</option>
              {PROVINCES.map(([v, label]) => (
                <option key={v} value={v}>
                  {label}
                </option>
              ))}
            </Select>
          </FormField>
          <FormField id="project-address" label="Ubicación" error={errors.address}>
            <Input {...bind('address')} />
          </FormField>
          <FormField id="project-start_date" label="Inicio" error={errors.start_date}>
            <Input type="date" {...bind('start_date')} />
          </FormField>
          <FormField
            id="project-estimated_end_date"
            label="Fin estimado"
            error={errors.estimated_end_date}
          >
            <Input type="date" {...bind('estimated_end_date')} />
          </FormField>
          <FormField
            id="project-contract_amount"
            label="Monto del contrato (B/.)"
            error={errors.contract_amount}
          >
            <Input type="number" min="0" step="0.01" {...bind('contract_amount')} />
          </FormField>
          {form.status === 'finished' && (
            <FormField id="project-actual_end_date" label="Fin real" error={errors.actual_end_date}>
              <Input type="date" {...bind('actual_end_date')} />
            </FormField>
          )}
        </div>
        <FormField id="project-description" label="Descripción" error={errors.description}>
          <Textarea {...bind('description')} />
        </FormField>
      </form>
    </Dialog>
  )
}
