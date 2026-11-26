import { useQueryClient } from '@tanstack/react-query'
import { CalendarDays, Check, Plus, X } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import type { LeaveVacationsListStatus, VacationRequest } from '@/api/generated/model'
import { useHrEmployeesList } from '@/api/generated/personal/personal'
import {
  getLeaveBalancesListQueryKey,
  getLeaveVacationsListQueryKey,
  useLeaveAdjustmentsCreate,
  useLeaveBalancesList,
  useLeaveVacationsApproveCreate,
  useLeaveVacationsCancelCreate,
  useLeaveVacationsCreate,
  useLeaveVacationsList,
  useLeaveVacationsRejectCreate,
} from '@/api/generated/vacaciones/vacaciones'
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
import { todayISO } from '@/features/employees/constants'
import { formatDate, formatMoney } from '@/lib/format'
import { useFormErrors } from '@/lib/use-form-errors'
import { cn } from '@/lib/utils'

const STATUS: Record<string, { label: string; variant: 'success' | 'neutral' | 'danger' }> = {
  requested: { label: 'Solicitada', variant: 'neutral' },
  approved: { label: 'Aprobada', variant: 'success' },
  rejected: { label: 'Rechazada', variant: 'danger' },
  cancelled: { label: 'Cancelada', variant: 'neutral' },
}

function useInvalidate() {
  const queryClient = useQueryClient()
  return () => {
    void queryClient.invalidateQueries({ queryKey: getLeaveVacationsListQueryKey() })
    void queryClient.invalidateQueries({ queryKey: getLeaveBalancesListQueryKey() })
  }
}

function EmployeePicker({
  value,
  onChange,
  error,
}: {
  value: string
  onChange: (v: string) => void
  error?: string
}) {
  const [search, setSearch] = useState('')
  const employees = useHrEmployeesList({
    status: 'active',
    search: search || undefined,
    ordering: 'last_name',
  })
  return (
    <FormField id="vac-employee" label="Empleado" error={error}>
      <div className="flex gap-2">
        <Input
          type="search"
          aria-label="Buscar empleado"
          placeholder="Buscar…"
          className="max-w-36"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <Select
          id="vac-employee"
          className="w-full"
          required
          value={value}
          onChange={(e) => onChange(e.target.value)}
        >
          <option value="">Selecciona…</option>
          {employees.data?.results.map((e) => (
            <option key={e.id} value={e.id}>
              {e.full_name} · {e.code}
            </option>
          ))}
        </Select>
      </div>
    </FormField>
  )
}

function RequestDialog({ onClose }: { onClose: () => void }) {
  const invalidate = useInvalidate()
  const [form, setForm] = useState({
    employee: '',
    start_date: todayISO(),
    days: '30',
    payment_mode: 'payroll',
    notes: '',
  })
  const { errors, error, reset, handle } = useFormErrors()
  const create = useLeaveVacationsCreate({
    mutation: {
      onSuccess: () => {
        invalidate()
        onClose()
      },
      onError: handle,
    },
  })
  const end = (() => {
    const d = new Date(`${form.start_date}T12:00:00`)
    if (!form.start_date || Number.isNaN(d.getTime())) return ''
    d.setDate(d.getDate() + Math.max(1, Number(form.days) || 1) - 1)
    return d.toISOString().slice(0, 10)
  })()
  const submit = (e: FormEvent) => {
    e.preventDefault()
    reset()
    create.mutate({
      data: {
        ...form,
        days: Number(form.days),
        payment_mode: form.payment_mode as VacationRequest['payment_mode'],
      },
    })
  }
  return (
    <Dialog
      open
      onOpenChange={(o) => !o && onClose()}
      title="Solicitud de vacaciones"
      description="Se cuentan días calendario. La aprobación verifica el saldo disponible."
      footer={
        <>
          <Button variant="outline" onClick={onClose}>
            Cancelar
          </Button>
          <Button type="submit" form="vac-form" loading={create.isPending}>
            Registrar solicitud
          </Button>
        </>
      }
    >
      <form id="vac-form" onSubmit={submit} className="space-y-4">
        {error && <Alert>{error}</Alert>}
        <EmployeePicker
          value={form.employee}
          onChange={(employee) => setForm({ ...form, employee })}
          error={errors.employee}
        />
        <div className="grid gap-4 sm:grid-cols-3">
          <FormField id="vac-start" label="Desde" error={errors.start_date}>
            <Input
              id="vac-start"
              type="date"
              required
              value={form.start_date}
              onChange={(e) => setForm({ ...form, start_date: e.target.value })}
            />
          </FormField>
          <FormField id="vac-days" label="Días" error={errors.days}>
            <Input
              id="vac-days"
              type="number"
              min="1"
              max="90"
              required
              value={form.days}
              onChange={(e) => setForm({ ...form, days: e.target.value })}
            />
          </FormField>
          <FormField id="vac-end" label="Hasta">
            <Input id="vac-end" type="date" disabled value={end} />
          </FormField>
        </div>
        <FormField id="vac-mode" label="Pago" error={errors.payment_mode}>
          <Select
            id="vac-mode"
            className="w-full"
            value={form.payment_mode}
            onChange={(e) => setForm({ ...form, payment_mode: e.target.value })}
          >
            <option value="payroll">En la planilla regular</option>
            <option value="separate">En una planilla de vacaciones (antes de salir)</option>
          </Select>
        </FormField>
        <FormField id="vac-notes" label="Observaciones" error={errors.notes}>
          <Input
            id="vac-notes"
            value={form.notes}
            onChange={(e) => setForm({ ...form, notes: e.target.value })}
          />
        </FormField>
      </form>
    </Dialog>
  )
}

function DecisionDialog({
  vacation,
  kind,
  onClose,
}: {
  vacation: VacationRequest
  kind: 'approve' | 'reject' | 'cancel'
  onClose: () => void
}) {
  const invalidate = useInvalidate()
  const [reason, setReason] = useState('')
  const { errors, error, reset, handle } = useFormErrors()
  const options = {
    mutation: {
      onSuccess: () => {
        invalidate()
        onClose()
      },
      onError: handle,
    },
  }
  const approve = useLeaveVacationsApproveCreate(options)
  const reject = useLeaveVacationsRejectCreate(options)
  const cancel = useLeaveVacationsCancelCreate(options)
  const config = {
    approve: { title: 'Aprobar vacaciones', label: 'Aprobar', mutation: approve, danger: false },
    reject: { title: 'Rechazar solicitud', label: 'Rechazar', mutation: reject, danger: true },
    cancel: {
      title: 'Cancelar vacaciones',
      label: 'Cancelar vacaciones',
      mutation: cancel,
      danger: true,
    },
  }[kind]
  return (
    <Dialog
      open
      onOpenChange={(o) => !o && onClose()}
      title={config.title}
      description={`${vacation.employee_name}: ${vacation.days} días, del ${formatDate(vacation.start_date)} al ${formatDate(vacation.end_date)}.`}
      footer={
        <>
          <Button variant="outline" onClick={onClose}>
            Volver
          </Button>
          <Button
            variant={config.danger ? 'danger' : 'primary'}
            loading={config.mutation.isPending}
            onClick={() => {
              reset()
              config.mutation.mutate({ id: vacation.id, data: { reason } })
            }}
          >
            {config.label}
          </Button>
        </>
      }
    >
      <div className="space-y-3">
        {error && <Alert>{error}</Alert>}
        {kind !== 'approve' && (
          <FormField
            id="dec-reason"
            label={kind === 'reject' ? 'Motivo del rechazo' : 'Motivo (opcional)'}
            error={errors.reason}
          >
            <Input id="dec-reason" value={reason} onChange={(e) => setReason(e.target.value)} />
          </FormField>
        )}
      </div>
    </Dialog>
  )
}

function AdjustmentDialog({
  employeeId,
  employeeName,
  onClose,
}: {
  employeeId: string
  employeeName: string
  onClose: () => void
}) {
  const invalidate = useInvalidate()
  const [form, setForm] = useState({ date: todayISO(), days: '', reason: '' })
  const { errors, error, reset, handle } = useFormErrors()
  const create = useLeaveAdjustmentsCreate({
    mutation: {
      onSuccess: () => {
        invalidate()
        onClose()
      },
      onError: handle,
    },
  })
  return (
    <Dialog
      open
      onOpenChange={(o) => !o && onClose()}
      title={`Ajustar saldo de ${employeeName}`}
      description="Para cargar el saldo con el que empieza a usar el sistema o vacaciones pagadas fuera de él. Usa días negativos para restar."
      footer={
        <>
          <Button variant="outline" onClick={onClose}>
            Cancelar
          </Button>
          <Button type="submit" form="adj-form" loading={create.isPending}>
            Guardar ajuste
          </Button>
        </>
      }
    >
      <form
        id="adj-form"
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault()
          reset()
          create.mutate({ data: { employee: employeeId, ...form } })
        }}
      >
        {error && <Alert>{error}</Alert>}
        <div className="grid gap-4 sm:grid-cols-2">
          <FormField id="adj-date" label="Fecha" error={errors.date}>
            <Input
              id="adj-date"
              type="date"
              required
              value={form.date}
              onChange={(e) => setForm({ ...form, date: e.target.value })}
            />
          </FormField>
          <FormField id="adj-days" label="Días (+/−)" error={errors.days}>
            <Input
              id="adj-days"
              type="number"
              step="0.5"
              required
              value={form.days}
              onChange={(e) => setForm({ ...form, days: e.target.value })}
            />
          </FormField>
        </div>
        <FormField id="adj-reason" label="Motivo" error={errors.reason}>
          <Input
            id="adj-reason"
            required
            value={form.reason}
            onChange={(e) => setForm({ ...form, reason: e.target.value })}
          />
        </FormField>
      </form>
    </Dialog>
  )
}

function RequestsTab() {
  const { can } = useAccess()
  const [status, setStatus] = useState('requested')
  const [page, setPage] = useState(1)
  const [decision, setDecision] = useState<{
    vacation: VacationRequest
    kind: 'approve' | 'reject' | 'cancel'
  } | null>(null)
  const list = useLeaveVacationsList({
    status: (status || undefined) as LeaveVacationsListStatus | undefined,
    page,
  })
  const rows = list.data?.results ?? []
  return (
    <div className="space-y-4">
      <Select
        aria-label="Estado"
        value={status}
        onChange={(e) => {
          setStatus(e.target.value)
          setPage(1)
        }}
      >
        <option value="requested">Pendientes de aprobar</option>
        <option value="approved">Aprobadas</option>
        <option value="rejected">Rechazadas</option>
        <option value="cancelled">Canceladas</option>
        <option value="">Todas</option>
      </Select>
      {list.isPending ? (
        <LoadingBlock />
      ) : rows.length === 0 ? (
        <EmptyState icon={CalendarDays} title="Sin solicitudes" />
      ) : (
        <>
          <Table>
            <THead>
              <tr>
                <TH>Empleado</TH>
                <TH>Período</TH>
                <TH className="text-right">Días</TH>
                <TH>Pago</TH>
                <TH>Estado</TH>
                <TH className="w-48" />
              </tr>
            </THead>
            <TBody>
              {rows.map((v) => {
                const st = STATUS[v.status]
                return (
                  <TR key={v.id}>
                    <TD>
                      <p className="font-medium">{v.employee_name}</p>
                      <p className="text-muted-foreground font-mono text-xs">{v.employee_code}</p>
                    </TD>
                    <TD className="whitespace-nowrap">
                      {formatDate(v.start_date)} – {formatDate(v.end_date)}
                    </TD>
                    <TD className="text-right tabular-nums">{v.days}</TD>
                    <TD className="text-xs">
                      {v.is_paid ? (
                        <span className="text-success">
                          Pagada {formatMoney(v.paid_amount)} (planilla #{v.paid_run_number})
                        </span>
                      ) : (
                        <span className="text-muted-foreground">{v.payment_mode_display}</span>
                      )}
                    </TD>
                    <TD>
                      <Badge variant={st.variant}>{st.label}</Badge>
                      {v.reject_reason && (
                        <p className="text-muted-foreground mt-1 text-xs">{v.reject_reason}</p>
                      )}
                    </TD>
                    <TD className="text-right whitespace-nowrap">
                      {v.status === 'requested' && can('leave.approve') && (
                        <>
                          <Button
                            size="sm"
                            variant="ghost"
                            onClick={() => setDecision({ vacation: v, kind: 'approve' })}
                          >
                            <Check className="size-4" /> Aprobar
                          </Button>
                          <Button
                            size="sm"
                            variant="ghost"
                            onClick={() => setDecision({ vacation: v, kind: 'reject' })}
                          >
                            <X className="size-4" /> Rechazar
                          </Button>
                        </>
                      )}
                      {(v.status === 'approved' || v.status === 'requested') &&
                        !v.is_paid &&
                        can('leave.manage') && (
                          <Button
                            size="sm"
                            variant="ghost"
                            onClick={() => setDecision({ vacation: v, kind: 'cancel' })}
                          >
                            Cancelar
                          </Button>
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
            noun={['solicitud', 'solicitudes']}
          />
        </>
      )}
      {decision && <DecisionDialog {...decision} onClose={() => setDecision(null)} />}
    </div>
  )
}

function BalancesTab() {
  const { can } = useAccess()
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const [adjusting, setAdjusting] = useState<{ id: string; name: string } | null>(null)
  const list = useLeaveBalancesList({ search: search || undefined, page })
  const rows = list.data?.results ?? []
  return (
    <div className="space-y-4">
      <Input
        type="search"
        placeholder="Buscar empleado…"
        aria-label="Buscar empleado"
        className="max-w-xs"
        value={search}
        onChange={(e) => {
          setSearch(e.target.value)
          setPage(1)
        }}
      />
      {list.isPending ? (
        <LoadingBlock />
      ) : (
        <>
          <Table>
            <THead>
              <tr>
                <TH>Empleado</TH>
                <TH>Ingreso</TH>
                <TH className="text-right">Ganados</TH>
                <TH className="text-right">Ajustes</TH>
                <TH className="text-right">Tomados</TH>
                <TH className="text-right">Programados</TH>
                <TH className="text-right">Disponibles</TH>
                {can('leave.manage') && <TH className="w-28" />}
              </tr>
            </THead>
            <TBody>
              {rows.map((b) => (
                <TR key={b.employee}>
                  <TD>
                    <p className="font-medium">{b.employee_name}</p>
                    <p className="text-muted-foreground font-mono text-xs">
                      {b.employee_code}
                      {b.pending_requests > 0 && ` · ${b.pending_requests} pendiente(s)`}
                    </p>
                  </TD>
                  <TD className="whitespace-nowrap">{formatDate(b.hire_date)}</TD>
                  <TD className="text-right tabular-nums">{b.earned}</TD>
                  <TD className="text-right tabular-nums">{b.adjustments}</TD>
                  <TD className="text-right tabular-nums">{b.taken}</TD>
                  <TD className="text-right tabular-nums">{b.scheduled}</TD>
                  <TD
                    className={cn(
                      'text-right font-semibold tabular-nums',
                      Number(b.available) < 0 && 'text-danger',
                    )}
                  >
                    {b.available}
                  </TD>
                  {can('leave.manage') && (
                    <TD className="text-right">
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => setAdjusting({ id: b.employee, name: b.employee_name })}
                      >
                        Ajustar
                      </Button>
                    </TD>
                  )}
                </TR>
              ))}
            </TBody>
          </Table>
          <Pager
            total={list.data?.count ?? 0}
            page={page}
            onPage={setPage}
            noun={['empleado', 'empleados']}
          />
        </>
      )}
      {adjusting && (
        <AdjustmentDialog
          employeeId={adjusting.id}
          employeeName={adjusting.name}
          onClose={() => setAdjusting(null)}
        />
      )}
    </div>
  )
}

export function VacationsPage() {
  const { can } = useAccess()
  const [tab, setTab] = useState<'requests' | 'balances'>('requests')
  const [creating, setCreating] = useState(false)
  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <PageHeader
        title="Vacaciones"
        description="30 días por cada 11 meses de trabajo. Las aprobadas se pagan en planilla y no cuentan como ausencias."
        actions={
          can('leave.manage') && (
            <Button onClick={() => setCreating(true)}>
              <Plus className="size-4" /> Nueva solicitud
            </Button>
          )
        }
      />
      <div role="tablist" className="flex gap-1 border-b">
        {(
          [
            ['requests', 'Solicitudes'],
            ['balances', 'Saldos'],
          ] as const
        ).map(([id, label]) => (
          <button
            key={id}
            role="tab"
            type="button"
            aria-selected={tab === id}
            onClick={() => setTab(id)}
            className={cn(
              'border-b-2 px-3 py-2 text-sm font-medium',
              tab === id
                ? 'border-primary text-foreground'
                : 'text-muted-foreground hover:text-foreground border-transparent',
            )}
          >
            {label}
          </button>
        ))}
      </div>
      {tab === 'requests' ? <RequestsTab /> : <BalancesTab />}
      {creating && <RequestDialog onClose={() => setCreating(false)} />}
    </div>
  )
}
