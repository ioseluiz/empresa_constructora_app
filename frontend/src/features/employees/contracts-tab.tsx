import { useQueryClient } from '@tanstack/react-query'
import { FileSignature, Pencil, Plus, TrendingUp, XCircle } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import type {
  Employee,
  EmploymentContract,
  EmploymentContractRequest,
  SalaryRecord,
} from '@/api/generated/model'
import {
  useOrgCbaCategoriesList,
  useOrgPositionsList,
} from '@/api/generated/organizacion/organizacion'
import {
  getHrAssignmentsListQueryKey,
  getHrContractsListQueryKey,
  getHrEmployeesListQueryKey,
  getHrEmployeesRetrieveQueryKey,
  getHrSalariesListQueryKey,
  useHrContractsCreate,
  useHrContractsEndCreate,
  useHrContractsList,
  useHrContractsPartialUpdate,
  useHrSalariesCreate,
  useHrSalariesList,
} from '@/api/generated/personal/personal'
import { useProjectsList } from '@/api/generated/proyectos/proyectos'
import { Alert } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import { Dialog } from '@/components/ui/dialog'
import { FormField } from '@/components/ui/form-field'
import { Input } from '@/components/ui/input'
import { EmptyState, LoadingBlock } from '@/components/ui/page'
import { Select } from '@/components/ui/select'
import { Table, TBody, TD, TH, THead, TR } from '@/components/ui/table'
import { Textarea } from '@/components/ui/textarea'
import { useAccess } from '@/features/access/use-access'
import { formatDate, formatMoney } from '@/lib/format'
import { useFormErrors } from '@/lib/use-form-errors'
import {
  CONTRACT_STATUS,
  CONTRACT_TYPES,
  PAY_BASES,
  PAY_FREQUENCIES,
  SHIFTS,
  todayISO,
} from './constants'
import { Options } from './employee-dialog'

function salaryText(record: SalaryRecord | null | undefined, contract: EmploymentContract) {
  if (!record) return '—'
  if (record.uses_cba_rate) return `Tarifa de convención (${contract.cba_category_name ?? '—'})`
  return contract.pay_basis === 'hourly'
    ? `${formatMoney(record.amount, 4)} por hora`
    : `${formatMoney(record.amount)} mensual`
}

function useInvalidate(employeeId: string) {
  const queryClient = useQueryClient()
  return () => {
    void queryClient.invalidateQueries({ queryKey: getHrContractsListQueryKey() })
    void queryClient.invalidateQueries({ queryKey: getHrSalariesListQueryKey() })
    void queryClient.invalidateQueries({ queryKey: getHrEmployeesRetrieveQueryKey(employeeId) })
    void queryClient.invalidateQueries({ queryKey: getHrEmployeesListQueryKey() })
    void queryClient.invalidateQueries({ queryKey: getHrAssignmentsListQueryKey() })
  }
}

function ContractDialog({
  employee,
  contract,
  onClose,
}: {
  employee: Employee
  contract?: EmploymentContract
  onClose: () => void
}) {
  const invalidate = useInvalidate(employee.id)
  const positions = useOrgPositionsList()
  const categories = useOrgCbaCategoriesList()
  const projects = useProjectsList({ ordering: 'code' })
  const [form, setForm] = useState({
    contract_type: contract?.contract_type ?? 'project',
    start_date:
      contract?.start_date ?? (employee.status === 'active' ? employee.hire_date : todayISO()),
    end_date: contract?.end_date ?? '',
    position: contract?.position ?? '',
    project: contract?.project ?? '',
    pay_frequency: contract?.pay_frequency ?? 'weekly',
    pay_basis: contract?.pay_basis ?? 'hourly',
    shift: contract?.shift ?? 'day',
    weekly_hours: contract?.weekly_hours ?? '48.0',
    applies_cba: contract?.applies_cba ?? false,
    cba_category: contract?.cba_category ?? '',
    notes: contract?.notes ?? '',
    initial_amount: '',
    initial_uses_cba_rate: false,
  })
  const { errors, error, reset, handle } = useFormErrors()
  const done = () => {
    invalidate()
    onClose()
  }
  const create = useHrContractsCreate({ mutation: { onSuccess: done, onError: handle } })
  const update = useHrContractsPartialUpdate({ mutation: { onSuccess: done, onError: handle } })
  const activeProjects = (projects.data?.results ?? []).filter(
    (p) => p.status !== 'finished' || p.id === contract?.project,
  )
  const selectedPosition = positions.data?.find((p) => p.id === form.position)

  const set =
    (key: keyof typeof form) =>
    (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) => {
      const value = e.target.value
      const next = { ...form, [key]: value }
      if (key === 'pay_basis') next.pay_frequency = value === 'hourly' ? 'weekly' : 'biweekly'
      if (key === 'position' && form.applies_cba && !form.cba_category) {
        next.cba_category = positions.data?.find((p) => p.id === value)?.cba_category ?? ''
      }
      setForm(next)
    }

  const submit = (e: FormEvent) => {
    e.preventDefault()
    reset()
    const usesCba = form.applies_cba && form.pay_basis === 'hourly' && form.initial_uses_cba_rate
    const data: EmploymentContractRequest = {
      employee: employee.id,
      contract_type: form.contract_type as EmploymentContractRequest['contract_type'],
      start_date: form.start_date,
      end_date: form.end_date || null,
      position: form.position,
      project: form.project || null,
      pay_frequency: form.pay_frequency as EmploymentContractRequest['pay_frequency'],
      pay_basis: form.pay_basis as EmploymentContractRequest['pay_basis'],
      shift: form.shift as EmploymentContractRequest['shift'],
      weekly_hours: form.weekly_hours,
      applies_cba: form.applies_cba,
      cba_category: form.applies_cba ? form.cba_category || null : null,
      notes: form.notes,
    }
    if (contract) {
      const { employee: _employee, ...changes } = data
      update.mutate({ id: contract.id, data: changes })
    } else {
      create.mutate({
        data: {
          ...data,
          initial_uses_cba_rate: usesCba,
          initial_amount: usesCba ? null : form.initial_amount || null,
        },
      })
    }
  }

  const id = (k: string) => `contract-${k}`
  return (
    <Dialog
      open
      size="lg"
      onOpenChange={(o) => !o && onClose()}
      title={contract ? 'Editar contrato' : 'Nuevo contrato'}
      description={
        contract
          ? 'Para cambiar el salario registra un aumento con su fecha de vigencia.'
          : 'Un contrato por obra determinada asigna automáticamente al empleado al proyecto.'
      }
      footer={
        <>
          <Button variant="outline" onClick={onClose}>
            Cancelar
          </Button>
          <Button type="submit" form="contract-form" loading={create.isPending || update.isPending}>
            Guardar
          </Button>
        </>
      }
    >
      <form
        id="contract-form"
        onSubmit={submit}
        className="max-h-[65vh] space-y-5 overflow-y-auto pr-1"
      >
        {error && <Alert>{error}</Alert>}
        <div className="grid gap-4 sm:grid-cols-2">
          <FormField id={id('contract_type')} label="Tipo de contrato" error={errors.contract_type}>
            <Select
              id={id('contract_type')}
              className="w-full"
              value={form.contract_type}
              onChange={set('contract_type')}
            >
              <Options items={CONTRACT_TYPES} />
            </Select>
          </FormField>
          <FormField id={id('position')} label="Puesto" error={errors.position}>
            <Select
              id={id('position')}
              className="w-full"
              required
              value={form.position}
              onChange={set('position')}
            >
              <option value="">Selecciona…</option>
              {positions.data
                ?.filter((p) => p.is_active || p.id === form.position)
                .map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
            </Select>
          </FormField>
          <FormField id={id('start_date')} label="Inicio" error={errors.start_date}>
            <Input
              id={id('start_date')}
              type="date"
              required
              value={form.start_date}
              onChange={set('start_date')}
            />
          </FormField>
          <FormField
            id={id('end_date')}
            label={form.contract_type === 'fixed_term' ? 'Fin' : 'Fin (opcional)'}
            error={errors.end_date}
          >
            <Input
              id={id('end_date')}
              type="date"
              required={form.contract_type === 'fixed_term'}
              value={form.end_date}
              onChange={set('end_date')}
            />
          </FormField>
          <FormField
            id={id('project')}
            label={form.contract_type === 'project' ? 'Obra' : 'Obra (opcional)'}
            error={errors.project}
          >
            <Select
              id={id('project')}
              className="w-full"
              required={form.contract_type === 'project'}
              value={form.project}
              onChange={set('project')}
            >
              <option value="">
                {form.contract_type === 'project' ? 'Selecciona…' : 'Oficina central'}
              </option>
              {activeProjects.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.code} · {p.name}
                </option>
              ))}
            </Select>
          </FormField>
          <FormField id={id('shift')} label="Jornada" error={errors.shift}>
            <Select id={id('shift')} className="w-full" value={form.shift} onChange={set('shift')}>
              <Options items={SHIFTS} />
            </Select>
          </FormField>
          <FormField id={id('pay_basis')} label="Base de pago" error={errors.pay_basis}>
            <Select
              id={id('pay_basis')}
              className="w-full"
              value={form.pay_basis}
              onChange={set('pay_basis')}
            >
              <Options items={PAY_BASES} />
            </Select>
          </FormField>
          <FormField
            id={id('pay_frequency')}
            label="Frecuencia de pago"
            error={errors.pay_frequency}
          >
            <Select
              id={id('pay_frequency')}
              className="w-full"
              value={form.pay_frequency}
              onChange={set('pay_frequency')}
            >
              <Options items={PAY_FREQUENCIES} />
            </Select>
          </FormField>
          <FormField id={id('weekly_hours')} label="Horas semanales" error={errors.weekly_hours}>
            <Input
              id={id('weekly_hours')}
              type="number"
              min="1"
              max="48"
              step="0.5"
              value={form.weekly_hours}
              onChange={set('weekly_hours')}
            />
          </FormField>
        </div>

        <div className="space-y-3 rounded-md border p-4">
          <label className="flex items-center gap-2 text-sm font-medium">
            <Checkbox
              checked={form.applies_cba}
              onChange={(e) =>
                setForm({
                  ...form,
                  applies_cba: e.target.checked,
                  cba_category: form.cba_category || selectedPosition?.cba_category || '',
                })
              }
            />
            Aplica la convención SUNTRACS–CAPAC
          </label>
          {form.applies_cba && (
            <FormField
              id={id('cba_category')}
              label="Categoría de la convención"
              error={errors.cba_category}
            >
              <Select
                id={id('cba_category')}
                className="w-full"
                value={form.cba_category}
                onChange={set('cba_category')}
              >
                <option value="">Selecciona…</option>
                {categories.data?.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                    {c.current_rate
                      ? ` · ${formatMoney(c.current_rate.hourly_rate, 4)}/h`
                      : ' · sin tarifa'}
                  </option>
                ))}
              </Select>
            </FormField>
          )}
        </div>

        {!contract && (
          <div className="space-y-3 rounded-md border p-4">
            <p className="text-sm font-medium">Salario inicial</p>
            {form.applies_cba && form.pay_basis === 'hourly' && (
              <label className="flex items-center gap-2 text-sm">
                <Checkbox
                  checked={form.initial_uses_cba_rate}
                  onChange={(e) => setForm({ ...form, initial_uses_cba_rate: e.target.checked })}
                />
                Pagar la tarifa de la convención vigente en cada fecha
              </label>
            )}
            {!(form.applies_cba && form.pay_basis === 'hourly' && form.initial_uses_cba_rate) && (
              <FormField
                id={id('initial_amount')}
                label={
                  form.pay_basis === 'hourly' ? 'Tarifa por hora (B/.)' : 'Salario mensual (B/.)'
                }
                error={errors.amount ?? errors.initial_amount}
              >
                <Input
                  id={id('initial_amount')}
                  type="number"
                  min="0"
                  step={form.pay_basis === 'hourly' ? '0.0001' : '0.01'}
                  required
                  value={form.initial_amount}
                  onChange={set('initial_amount')}
                />
              </FormField>
            )}
            {errors.uses_cba_rate && <p className="text-danger text-xs">{errors.uses_cba_rate}</p>}
          </div>
        )}
        <FormField id={id('notes')} label="Observaciones" error={errors.notes}>
          <Textarea id={id('notes')} value={form.notes} onChange={set('notes')} />
        </FormField>
      </form>
    </Dialog>
  )
}

function RaiseDialog({
  contract,
  employeeId,
  onClose,
}: {
  contract: EmploymentContract
  employeeId: string
  onClose: () => void
}) {
  const invalidate = useInvalidate(employeeId)
  const [form, setForm] = useState({
    valid_from: todayISO(),
    amount: '',
    uses_cba_rate: false,
    reason: '',
  })
  const { errors, error, reset, handle } = useFormErrors()
  const create = useHrSalariesCreate({
    mutation: {
      onSuccess: () => {
        invalidate()
        onClose()
      },
      onError: handle,
    },
  })
  const canUseCba = contract.applies_cba && contract.pay_basis === 'hourly'
  const submit = (e: FormEvent) => {
    e.preventDefault()
    reset()
    create.mutate({
      data: {
        contract: contract.id,
        valid_from: form.valid_from,
        uses_cba_rate: form.uses_cba_rate,
        amount: form.uses_cba_rate ? null : form.amount,
        reason: form.reason,
      },
    })
  }
  return (
    <Dialog
      open
      onOpenChange={(o) => !o && onClose()}
      title="Registrar cambio de salario"
      description={`Actual: ${salaryText(contract.current_salary, contract)}. El historial anterior se conserva.`}
      footer={
        <>
          <Button variant="outline" onClick={onClose}>
            Cancelar
          </Button>
          <Button type="submit" form="raise-form" loading={create.isPending}>
            Guardar
          </Button>
        </>
      }
    >
      <form id="raise-form" onSubmit={submit} className="space-y-4">
        {error && <Alert>{error}</Alert>}
        <FormField id="raise-valid_from" label="Vigente desde" error={errors.valid_from}>
          <Input
            id="raise-valid_from"
            type="date"
            required
            value={form.valid_from}
            onChange={(e) => setForm({ ...form, valid_from: e.target.value })}
          />
        </FormField>
        {canUseCba && (
          <label className="flex items-center gap-2 text-sm">
            <Checkbox
              checked={form.uses_cba_rate}
              onChange={(e) => setForm({ ...form, uses_cba_rate: e.target.checked })}
            />
            Usar la tarifa de la convención
          </label>
        )}
        {!form.uses_cba_rate && (
          <FormField
            id="raise-amount"
            label={
              contract.pay_basis === 'hourly'
                ? 'Nueva tarifa por hora (B/.)'
                : 'Nuevo salario mensual (B/.)'
            }
            error={errors.amount}
          >
            <Input
              id="raise-amount"
              type="number"
              min="0"
              step={contract.pay_basis === 'hourly' ? '0.0001' : '0.01'}
              required
              value={form.amount}
              onChange={(e) => setForm({ ...form, amount: e.target.value })}
            />
          </FormField>
        )}
        <FormField id="raise-reason" label="Motivo" error={errors.reason}>
          <Input
            id="raise-reason"
            placeholder="Aumento por desempeño, ajuste de convención…"
            value={form.reason}
            onChange={(e) => setForm({ ...form, reason: e.target.value })}
          />
        </FormField>
      </form>
    </Dialog>
  )
}

function EndDialog({
  contract,
  employeeId,
  onClose,
}: {
  contract: EmploymentContract
  employeeId: string
  onClose: () => void
}) {
  const invalidate = useInvalidate(employeeId)
  const [form, setForm] = useState({ end_date: contract.end_date ?? todayISO(), reason: '' })
  const { errors, error, reset, handle } = useFormErrors()
  const end = useHrContractsEndCreate({
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
      title="Terminar contrato"
      description="Si no tiene otro contrato vigente, el empleado quedará retirado y se cerrarán sus asignaciones. El cálculo de prestaciones (liquidación) llegará en un próximo módulo."
      footer={
        <>
          <Button variant="outline" onClick={onClose}>
            Cancelar
          </Button>
          <Button type="submit" form="end-form" variant="danger" loading={end.isPending}>
            Terminar contrato
          </Button>
        </>
      }
    >
      <form
        id="end-form"
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault()
          reset()
          end.mutate({ id: contract.id, data: form })
        }}
      >
        {error && <Alert>{error}</Alert>}
        <FormField id="end-date" label="Último día laborado" error={errors.end_date}>
          <Input
            id="end-date"
            type="date"
            required
            value={form.end_date}
            onChange={(e) => setForm({ ...form, end_date: e.target.value })}
          />
        </FormField>
        <FormField id="end-reason" label="Motivo" error={errors.reason}>
          <Input
            id="end-reason"
            required
            placeholder="Renuncia, fin de obra, mutuo acuerdo…"
            value={form.reason}
            onChange={(e) => setForm({ ...form, reason: e.target.value })}
          />
        </FormField>
      </form>
    </Dialog>
  )
}

function SalaryHistory({ contract }: { contract: EmploymentContract }) {
  const history = useHrSalariesList({ contract: contract.id })
  if (history.isPending) return <LoadingBlock />
  return (
    <Table>
      <THead>
        <tr>
          <TH>Vigente desde</TH>
          <TH>Monto</TH>
          <TH>Motivo</TH>
        </tr>
      </THead>
      <TBody>
        {history.data?.map((r) => (
          <TR key={r.id}>
            <TD className="whitespace-nowrap">{formatDate(r.valid_from)}</TD>
            <TD className="tabular-nums">{salaryText(r, contract)}</TD>
            <TD className="text-muted-foreground">{r.reason || '—'}</TD>
          </TR>
        ))}
      </TBody>
    </Table>
  )
}

type Modal =
  { kind: 'new' } | { kind: 'edit' | 'raise' | 'end'; contract: EmploymentContract } | null

export function ContractsTab({ employee }: { employee: Employee }) {
  const { can } = useAccess()
  const canManage = can('hr.employee.manage')
  const canSalary = can('hr.salary.view')
  const [modal, setModal] = useState<Modal>(null)
  const [expanded, setExpanded] = useState<string | null>(null)
  const contracts = useHrContractsList({ employee: employee.id })
  const rows = contracts.data ?? []

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-4">
        <p className="text-muted-foreground text-sm">
          Historial de contratos. La planilla usa el contrato y el salario vigentes en cada fecha.
        </p>
        {canManage && canSalary && (
          <Button onClick={() => setModal({ kind: 'new' })}>
            <Plus className="size-4" /> Nuevo contrato
          </Button>
        )}
      </div>
      {contracts.isPending ? (
        <LoadingBlock />
      ) : rows.length === 0 ? (
        <EmptyState
          icon={FileSignature}
          title="Sin contratos"
          description="Registra el contrato de trabajo para poder incluirlo en planilla."
        />
      ) : (
        rows.map((c) => {
          const st = CONTRACT_STATUS[c.status]
          const active = c.status === 'active'
          return (
            <Card key={c.id}>
              <CardContent className="space-y-4 pt-5">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      <p className="font-medium">{c.contract_type_display}</p>
                      <Badge variant={st.variant}>{st.label}</Badge>
                      {c.applies_cba && <Badge>Convención</Badge>}
                    </div>
                    <p className="text-muted-foreground text-sm">
                      {formatDate(c.start_date)} –{' '}
                      {c.end_date ? formatDate(c.end_date) : 'sin fecha de fin'}
                      {c.end_reason && ` · ${c.end_reason}`}
                    </p>
                  </div>
                  {canManage && active && (
                    <div className="flex flex-wrap gap-2">
                      {canSalary && (
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => setModal({ kind: 'raise', contract: c })}
                        >
                          <TrendingUp className="size-4" /> Cambio de salario
                        </Button>
                      )}
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => setModal({ kind: 'edit', contract: c })}
                      >
                        <Pencil className="size-4" /> Editar
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => setModal({ kind: 'end', contract: c })}
                      >
                        <XCircle className="size-4" /> Terminar
                      </Button>
                    </div>
                  )}
                </div>
                <dl className="grid gap-4 text-sm sm:grid-cols-3 lg:grid-cols-6">
                  {(
                    [
                      ['Puesto', c.position_name],
                      [
                        'Centro de costo',
                        c.project_code ? `${c.cost_center_code} (obra)` : c.cost_center_code,
                      ],
                      ['Jornada', `${c.shift_display} · ${Number(c.weekly_hours)} h/sem`],
                      ['Pago', `${c.pay_basis_display} · ${c.pay_frequency_display}`],
                      ['Categoría', c.cba_category_name ?? '—'],
                      ['Salario', canSalary ? salaryText(c.current_salary, c) : 'Restringido'],
                    ] as [string, string][]
                  ).map(([term, value]) => (
                    <div key={term} className="space-y-0.5">
                      <dt className="text-muted-foreground text-xs">{term}</dt>
                      <dd className="font-medium">{value}</dd>
                    </div>
                  ))}
                </dl>
                {canSalary && (
                  <div>
                    <button
                      type="button"
                      className="text-primary text-sm hover:underline"
                      onClick={() => setExpanded(expanded === c.id ? null : c.id)}
                    >
                      {expanded === c.id ? 'Ocultar historial salarial' : 'Ver historial salarial'}
                    </button>
                    {expanded === c.id && (
                      <div className="mt-3">
                        <SalaryHistory contract={c} />
                      </div>
                    )}
                  </div>
                )}
              </CardContent>
            </Card>
          )
        })
      )}
      {modal?.kind === 'new' && (
        <ContractDialog employee={employee} onClose={() => setModal(null)} />
      )}
      {modal?.kind === 'edit' && (
        <ContractDialog
          employee={employee}
          contract={modal.contract}
          onClose={() => setModal(null)}
        />
      )}
      {modal?.kind === 'raise' && (
        <RaiseDialog
          contract={modal.contract}
          employeeId={employee.id}
          onClose={() => setModal(null)}
        />
      )}
      {modal?.kind === 'end' && (
        <EndDialog
          contract={modal.contract}
          employeeId={employee.id}
          onClose={() => setModal(null)}
        />
      )}
    </div>
  )
}
