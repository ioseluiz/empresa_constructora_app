import { useQueryClient } from '@tanstack/react-query'
import { FileSpreadsheet, Plus } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import type { PayrollRunRequest, PayrollRunsListStatus } from '@/api/generated/model'
import {
  getPayrollRunsListQueryKey,
  usePayrollRunsCreate,
  usePayrollRunsList,
} from '@/api/generated/planilla/planilla'
import { useProjectsList } from '@/api/generated/proyectos/proyectos'
import { Alert } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Dialog } from '@/components/ui/dialog'
import { FormField } from '@/components/ui/form-field'
import { Input } from '@/components/ui/input'
import { EmptyState, LoadingBlock, PageHeader } from '@/components/ui/page'
import { Pager } from '@/components/ui/pager'
import { Select } from '@/components/ui/select'
import { Table, TBody, TD, TH, THead, TR } from '@/components/ui/table'
import { useAccess } from '@/features/access/use-access'
import { formatDate, formatMoney } from '@/lib/format'
import { useFormErrors } from '@/lib/use-form-errors'
import { RUN_STATUS, suggestedPeriod } from './constants'
import { PayrollTabs } from './payroll-tabs'

function NewRunDialog({ onClose }: { onClose: () => void }) {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const { isOwner } = useAccess()
  const projects = useProjectsList({ ordering: 'code', status: 'active' })
  const initial = suggestedPeriod('weekly')
  const [form, setForm] = useState({
    scope: 'project',
    project: '',
    frequency: 'weekly',
    period_start: initial.start,
    period_end: initial.end,
    pay_date: initial.pay,
  })
  const { errors, error, reset, handle } = useFormErrors()
  const create = usePayrollRunsCreate({
    mutation: {
      onSuccess: (run) => {
        void queryClient.invalidateQueries({ queryKey: getPayrollRunsListQueryKey() })
        void navigate(`/planilla/corridas/${run.id}`)
      },
      onError: handle,
    },
  })
  const setFrequency = (frequency: string) => {
    const p = suggestedPeriod(frequency)
    setForm({ ...form, frequency, period_start: p.start, period_end: p.end, pay_date: p.pay })
  }
  const submit = (e: FormEvent) => {
    e.preventDefault()
    reset()
    create.mutate({
      data: {
        ...form,
        run_type: 'regular',
        scope: form.scope as PayrollRunRequest['scope'],
        frequency: form.frequency as PayrollRunRequest['frequency'],
        project: form.scope === 'project' ? form.project || null : null,
      },
    })
  }
  const set =
    (key: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
      setForm({ ...form, [key]: e.target.value })
  return (
    <Dialog
      open
      onOpenChange={(o) => !o && onClose()}
      title="Nueva planilla"
      description="Incluye a los empleados cuyo contrato tiene la frecuencia elegida y pertenece al alcance. Luego podrás calcularla y revisarla antes de aprobar."
      footer={
        <>
          <Button variant="outline" onClick={onClose}>
            Cancelar
          </Button>
          <Button type="submit" form="run-form" loading={create.isPending}>
            Crear borrador
          </Button>
        </>
      }
    >
      <form id="run-form" onSubmit={submit} className="space-y-4">
        {error && <Alert>{error}</Alert>}
        <div className="grid gap-4 sm:grid-cols-2">
          <FormField id="run-scope" label="Alcance" error={errors.scope}>
            <Select id="run-scope" className="w-full" value={form.scope} onChange={set('scope')}>
              <option value="project">Un proyecto</option>
              <option value="office">Oficina central</option>
              <option value="company">Toda la empresa</option>
            </Select>
          </FormField>
          <FormField id="run-frequency" label="Frecuencia" error={errors.frequency}>
            <Select
              id="run-frequency"
              className="w-full"
              value={form.frequency}
              onChange={(e) => setFrequency(e.target.value)}
            >
              <option value="weekly">Semanal (obra)</option>
              <option value="biweekly">Quincenal</option>
              <option value="monthly">Mensual</option>
            </Select>
          </FormField>
        </div>
        {form.scope === 'project' && (
          <FormField id="run-project" label="Proyecto" error={errors.project}>
            <Select
              id="run-project"
              className="w-full"
              required
              value={form.project}
              onChange={set('project')}
            >
              <option value="">Selecciona…</option>
              {projects.data?.results.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.code} · {p.name}
                </option>
              ))}
            </Select>
          </FormField>
        )}
        {form.scope !== 'project' && !isOwner && (
          <p className="text-muted-foreground text-xs">Requiere permiso sobre toda la empresa.</p>
        )}
        <div className="grid gap-4 sm:grid-cols-3">
          <FormField id="run-start" label="Desde" error={errors.period_start}>
            <Input
              id="run-start"
              type="date"
              required
              value={form.period_start}
              onChange={set('period_start')}
            />
          </FormField>
          <FormField id="run-end" label="Hasta" error={errors.period_end}>
            <Input
              id="run-end"
              type="date"
              required
              value={form.period_end}
              onChange={set('period_end')}
            />
          </FormField>
          <FormField id="run-pay" label="Fecha de pago" error={errors.pay_date}>
            <Input
              id="run-pay"
              type="date"
              required
              value={form.pay_date}
              onChange={set('pay_date')}
            />
          </FormField>
        </div>
      </form>
    </Dialog>
  )
}

export function RunsPage() {
  const { can } = useAccess()
  const [status, setStatus] = useState('')
  const [page, setPage] = useState(1)
  const [creating, setCreating] = useState(false)
  const list = usePayrollRunsList({
    status: (status || undefined) as PayrollRunsListStatus | undefined,
    page,
  })
  const rows = list.data?.results ?? []

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <PageHeader
        title="Planilla"
        description="Planillas por proyecto y oficina central. Al aprobarlas, las horas quedan pagadas y la planilla ya no cambia."
        actions={
          can('payroll.calculate') && (
            <Button onClick={() => setCreating(true)}>
              <Plus className="size-4" /> Nueva planilla
            </Button>
          )
        }
      />
      <PayrollTabs />
      <Select
        aria-label="Estado"
        value={status}
        onChange={(e) => {
          setStatus(e.target.value)
          setPage(1)
        }}
      >
        <option value="">Todos los estados</option>
        {Object.entries(RUN_STATUS).map(([v, { label }]) => (
          <option key={v} value={v}>
            {label}
          </option>
        ))}
      </Select>
      {list.isPending ? (
        <LoadingBlock />
      ) : rows.length === 0 ? (
        <EmptyState
          icon={FileSpreadsheet}
          title="Aún no hay planillas"
          description="Crea la primera planilla del período."
        />
      ) : (
        <>
          <Table>
            <THead>
              <tr>
                <TH>Planilla</TH>
                <TH>Período</TH>
                <TH>Pago</TH>
                <TH className="text-right">Empleados</TH>
                <TH className="text-right">Bruto</TH>
                <TH className="text-right">Neto</TH>
                <TH>Estado</TH>
              </tr>
            </THead>
            <TBody>
              {rows.map((r) => {
                const st = RUN_STATUS[r.status]
                return (
                  <TR key={r.id}>
                    <TD>
                      <Link
                        to={`/planilla/corridas/${r.id}`}
                        className="text-primary font-medium hover:underline"
                      >
                        #{r.number} · {r.scope === 'project' ? r.project_code : r.scope_display}
                      </Link>
                      <p className="text-muted-foreground text-xs">{r.frequency_display}</p>
                    </TD>
                    <TD className="whitespace-nowrap">
                      {formatDate(r.period_start)} – {formatDate(r.period_end)}
                    </TD>
                    <TD className="whitespace-nowrap">{formatDate(r.pay_date)}</TD>
                    <TD className="text-right tabular-nums">{r.employee_count}</TD>
                    <TD className="text-right tabular-nums">{formatMoney(r.gross)}</TD>
                    <TD className="text-right font-medium tabular-nums">{formatMoney(r.net)}</TD>
                    <TD>
                      <Badge variant={st.variant}>{st.label}</Badge>
                      {r.error_count > 0 && (
                        <Badge className="ml-1" variant="danger">
                          {r.error_count} con error
                        </Badge>
                      )}
                    </TD>
                  </TR>
                )
              })}
            </TBody>
          </Table>
          <Pager
            total={list.data?.count ?? 0}
            page={page}
            onPage={setPage}
            noun={['planilla', 'planillas']}
          />
        </>
      )}
      {creating && <NewRunDialog onClose={() => setCreating(false)} />}
    </div>
  )
}
