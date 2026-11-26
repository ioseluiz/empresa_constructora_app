import { useQueryClient } from '@tanstack/react-query'
import { HandCoins, Plus } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import type { Employee, RecurringDeduction } from '@/api/generated/model'
import {
  getPayrollDeductionsListQueryKey,
  usePayrollConceptsList,
  usePayrollDeductionsCreate,
  usePayrollDeductionsList,
  usePayrollDeductionsPartialUpdate,
} from '@/api/generated/planilla/planilla'
import { Alert } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Switch } from '@/components/ui/checkbox'
import { Dialog } from '@/components/ui/dialog'
import { FormField } from '@/components/ui/form-field'
import { Input } from '@/components/ui/input'
import { EmptyState, LoadingBlock } from '@/components/ui/page'
import { Select } from '@/components/ui/select'
import { Table, TBody, TD, TH, THead, TR } from '@/components/ui/table'
import { useAccess } from '@/features/access/use-access'
import { formatDate, formatMoney } from '@/lib/format'
import { useFormErrors } from '@/lib/use-form-errors'
import { todayISO } from './constants'

const STATUTORY = new Set(['CSS', 'SE', 'ISR', 'CUOTA_SINDICAL'])

function DeductionDialog({
  employee,
  deduction,
  onClose,
}: {
  employee: Employee
  deduction?: RecurringDeduction
  onClose: () => void
}) {
  const queryClient = useQueryClient()
  const concepts = usePayrollConceptsList({ kind: 'deduction', is_active: true })
  const [form, setForm] = useState({
    concept: deduction?.concept ?? '',
    amount_per_period: deduction?.amount_per_period ?? '',
    total_amount: deduction?.total_amount ?? '',
    start_date: deduction?.start_date ?? todayISO(),
    end_date: deduction?.end_date ?? '',
    creditor: deduction?.creditor ?? '',
    reference: deduction?.reference ?? '',
    is_active: deduction?.is_active ?? true,
  })
  const { errors, error, reset, handle } = useFormErrors()
  const onSuccess = () => {
    void queryClient.invalidateQueries({ queryKey: getPayrollDeductionsListQueryKey() })
    onClose()
  }
  const create = usePayrollDeductionsCreate({ mutation: { onSuccess, onError: handle } })
  const update = usePayrollDeductionsPartialUpdate({ mutation: { onSuccess, onError: handle } })
  const options = (concepts.data ?? []).filter((c) => !STATUTORY.has(c.code))
  const legal = options.find((c) => c.id === form.concept)?.is_legal_order
  const submit = (e: FormEvent) => {
    e.preventDefault()
    reset()
    const data = {
      ...form,
      employee: employee.id,
      total_amount: form.total_amount || null,
      end_date: form.end_date || null,
    }
    if (deduction) update.mutate({ id: deduction.id, data })
    else create.mutate({ data })
  }
  const set =
    (key: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
      setForm({ ...form, [key]: e.target.value })
  return (
    <Dialog
      open
      onOpenChange={(o) => !o && onClose()}
      title={deduction ? 'Editar descuento' : 'Nuevo descuento'}
      description="Se aplica en cada planilla del empleado mientras esté vigente. Los préstamos se detienen al completar el monto total."
      footer={
        <>
          <Button variant="outline" onClick={onClose}>
            Cancelar
          </Button>
          <Button
            type="submit"
            form="deduction-form"
            loading={create.isPending || update.isPending}
          >
            Guardar
          </Button>
        </>
      }
    >
      <form id="deduction-form" onSubmit={submit} className="space-y-4">
        {error && <Alert>{error}</Alert>}
        <FormField id="ded-concept" label="Concepto" error={errors.concept}>
          <Select
            id="ded-concept"
            className="w-full"
            required
            value={form.concept}
            onChange={set('concept')}
          >
            <option value="">Selecciona…</option>
            {options.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </Select>
        </FormField>
        <div className="grid gap-4 sm:grid-cols-2">
          <FormField
            id="ded-amount"
            label="Cuota por planilla (B/.)"
            error={errors.amount_per_period}
          >
            <Input
              id="ded-amount"
              type="number"
              min="0.01"
              step="0.01"
              required
              value={form.amount_per_period}
              onChange={set('amount_per_period')}
            />
          </FormField>
          <FormField id="ded-total" label="Monto total (opcional)" error={errors.total_amount}>
            <Input
              id="ded-total"
              type="number"
              min="0.01"
              step="0.01"
              placeholder="Sin límite"
              value={form.total_amount ?? ''}
              onChange={set('total_amount')}
            />
          </FormField>
          <FormField id="ded-start" label="Desde" error={errors.start_date}>
            <Input
              id="ded-start"
              type="date"
              required
              value={form.start_date}
              onChange={set('start_date')}
            />
          </FormField>
          <FormField id="ded-end" label="Hasta (opcional)" error={errors.end_date}>
            <Input
              id="ded-end"
              type="date"
              value={form.end_date ?? ''}
              onChange={set('end_date')}
            />
          </FormField>
          <FormField id="ded-creditor" label="Acreedor / beneficiario" error={errors.creditor}>
            <Input id="ded-creditor" value={form.creditor} onChange={set('creditor')} />
          </FormField>
          <FormField
            id="ded-ref"
            label={legal ? 'Nº de oficio o resolución' : 'Referencia'}
            error={errors.reference}
          >
            <Input
              id="ded-ref"
              required={!!legal}
              value={form.reference}
              onChange={set('reference')}
            />
          </FormField>
        </div>
        <label className="flex items-center gap-2 text-sm">
          <Switch
            checked={form.is_active}
            onCheckedChange={(v) => setForm({ ...form, is_active: v })}
          />{' '}
          Activo
        </label>
      </form>
    </Dialog>
  )
}

export function DeductionsTab({ employee }: { employee: Employee }) {
  const { can } = useAccess()
  const canEdit = can('payroll.config')
  const deductions = usePayrollDeductionsList({ employee: employee.id })
  const [editing, setEditing] = useState<RecurringDeduction | 'new' | null>(null)
  const rows = deductions.data ?? []
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-4">
        <p className="text-muted-foreground text-sm">
          Préstamos, pensión alimenticia, embargos y otros descuentos. Las órdenes judiciales se
          aplican primero.
        </p>
        {canEdit && (
          <Button onClick={() => setEditing('new')}>
            <Plus className="size-4" /> Nuevo descuento
          </Button>
        )}
      </div>
      {deductions.isPending ? (
        <LoadingBlock />
      ) : rows.length === 0 ? (
        <EmptyState icon={HandCoins} title="Sin descuentos" />
      ) : (
        <Table>
          <THead>
            <tr>
              <TH>Concepto</TH>
              <TH className="text-right">Cuota</TH>
              <TH className="text-right">Saldo</TH>
              <TH>Vigencia</TH>
              <TH>Estado</TH>
            </tr>
          </THead>
          <TBody>
            {rows.map((d) => (
              <TR
                key={d.id}
                className={canEdit ? 'cursor-pointer' : undefined}
                onClick={() => canEdit && setEditing(d)}
              >
                <TD>
                  <p className="font-medium">{d.concept_name}</p>
                  <p className="text-muted-foreground text-xs">
                    {[d.creditor, d.reference].filter(Boolean).join(' · ') || '—'}
                  </p>
                </TD>
                <TD className="text-right tabular-nums">{formatMoney(d.amount_per_period)}</TD>
                <TD className="text-right tabular-nums">
                  {d.balance === null
                    ? '—'
                    : `${formatMoney(d.balance)} de ${formatMoney(d.total_amount)}`}
                </TD>
                <TD className="whitespace-nowrap">
                  {formatDate(d.start_date)} – {d.end_date ? formatDate(d.end_date) : 'sin fin'}
                </TD>
                <TD>
                  <Badge variant={d.is_active ? 'success' : 'neutral'}>
                    {d.is_active ? 'Activo' : 'Inactivo'}
                  </Badge>
                </TD>
              </TR>
            ))}
          </TBody>
        </Table>
      )}
      {editing && (
        <DeductionDialog
          employee={employee}
          deduction={editing === 'new' ? undefined : editing}
          onClose={() => setEditing(null)}
        />
      )}
    </div>
  )
}
