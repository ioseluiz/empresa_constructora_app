import { useQueryClient } from '@tanstack/react-query'
import { Check, Plus } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import type { PayrollConcept } from '@/api/generated/model'
import {
  getPayrollConceptsListQueryKey,
  usePayrollConceptsCreate,
  usePayrollConceptsList,
  usePayrollConceptsPartialUpdate,
} from '@/api/generated/planilla/planilla'
import { Alert } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox, Switch } from '@/components/ui/checkbox'
import { Dialog } from '@/components/ui/dialog'
import { FormField } from '@/components/ui/form-field'
import { Input } from '@/components/ui/input'
import { LoadingBlock, PageHeader } from '@/components/ui/page'
import { Table, TBody, TD, TH, THead, TR } from '@/components/ui/table'
import { useAccess } from '@/features/access/use-access'
import { useFormErrors } from '@/lib/use-form-errors'
import { PayrollTabs } from './payroll-tabs'

const KINDS: [string, string][] = [
  ['earning', 'Ingresos'],
  ['deduction', 'Deducciones'],
  ['employer', 'Aportes patronales'],
  ['provision', 'Provisiones'],
]

function ConceptDialog({ concept, onClose }: { concept?: PayrollConcept; onClose: () => void }) {
  const queryClient = useQueryClient()
  const locked = concept?.is_system ?? false
  const [form, setForm] = useState({
    code: concept?.code ?? '',
    name: concept?.name ?? '',
    priority: String(concept?.priority ?? 60),
    accounting_account: concept?.accounting_account ?? '',
    is_legal_order: concept?.is_legal_order ?? false,
    is_active: concept?.is_active ?? true,
  })
  const { errors, error, reset, handle } = useFormErrors()
  const onSuccess = () => {
    void queryClient.invalidateQueries({ queryKey: getPayrollConceptsListQueryKey() })
    onClose()
  }
  const create = usePayrollConceptsCreate({ mutation: { onSuccess, onError: handle } })
  const update = usePayrollConceptsPartialUpdate({ mutation: { onSuccess, onError: handle } })
  const submit = (e: FormEvent) => {
    e.preventDefault()
    reset()
    const base = {
      name: form.name,
      priority: Number(form.priority),
      accounting_account: form.accounting_account,
      is_active: form.is_active,
    }
    if (concept)
      update.mutate({
        id: concept.id,
        data: locked ? base : { ...base, is_legal_order: form.is_legal_order },
      })
    else
      create.mutate({
        data: { ...base, code: form.code, kind: 'deduction', is_legal_order: form.is_legal_order },
      })
  }
  return (
    <Dialog
      open
      onOpenChange={(o) => !o && onClose()}
      title={concept ? `Editar ${concept.name}` : 'Nueva deducción'}
      description={
        locked
          ? 'Concepto del sistema: su tratamiento legal no se modifica; puedes ajustar el nombre, la prioridad y la cuenta contable.'
          : 'Descuentos propios de la empresa (uniformes, adelantos, cooperativa…).'
      }
      footer={
        <>
          <Button variant="outline" onClick={onClose}>
            Cancelar
          </Button>
          <Button type="submit" form="concept-form" loading={create.isPending || update.isPending}>
            Guardar
          </Button>
        </>
      }
    >
      <form id="concept-form" onSubmit={submit} className="space-y-4">
        {error && <Alert>{error}</Alert>}
        <div className="grid gap-4 sm:grid-cols-[8rem_1fr]">
          <FormField id="cpt-code" label="Código" error={errors.code}>
            <Input
              id="cpt-code"
              required
              disabled={!!concept}
              value={form.code}
              onChange={(e) => setForm({ ...form, code: e.target.value })}
            />
          </FormField>
          <FormField id="cpt-name" label="Nombre" error={errors.name}>
            <Input
              id="cpt-name"
              required
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
            />
          </FormField>
          <FormField id="cpt-priority" label="Prioridad" error={errors.priority}>
            <Input
              id="cpt-priority"
              type="number"
              min="1"
              value={form.priority}
              onChange={(e) => setForm({ ...form, priority: e.target.value })}
            />
          </FormField>
          <FormField id="cpt-account" label="Cuenta contable" error={errors.accounting_account}>
            <Input
              id="cpt-account"
              placeholder="Para la contabilidad (fase 2)"
              value={form.accounting_account}
              onChange={(e) => setForm({ ...form, accounting_account: e.target.value })}
            />
          </FormField>
        </div>
        {!locked && (
          <label className="flex items-center gap-2 text-sm">
            <Checkbox
              checked={form.is_legal_order}
              onChange={(e) => setForm({ ...form, is_legal_order: e.target.checked })}
            />
            Es una orden judicial (se descuenta antes que los demás)
          </label>
        )}
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

export function ConceptsPage() {
  const { can } = useAccess()
  const canEdit = can('payroll.config')
  const concepts = usePayrollConceptsList()
  const [editing, setEditing] = useState<PayrollConcept | 'new' | null>(null)
  const flag = (on: boolean) =>
    on ? <Check className="text-success size-4" aria-label="Sí" /> : null

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <PageHeader
        title="Planilla"
        description="Conceptos de ingreso, deducción, aportes y provisiones, con su tratamiento fiscal y cuenta contable."
        actions={
          canEdit && (
            <Button onClick={() => setEditing('new')}>
              <Plus className="size-4" /> Nueva deducción
            </Button>
          )
        }
      />
      <PayrollTabs />
      {concepts.isPending ? (
        <LoadingBlock />
      ) : (
        KINDS.map(([kind, title]) => {
          const rows = concepts.data?.filter((c) => c.kind === kind) ?? []
          if (rows.length === 0) return null
          return (
            <section key={kind} className="space-y-2">
              <h2 className="text-sm font-semibold">{title}</h2>
              <Table>
                <THead>
                  <tr>
                    <TH>Concepto</TH>
                    {kind === 'earning' && (
                      <>
                        <TH className="w-20 text-center">CSS</TH>
                        <TH className="w-20 text-center">S. Educ.</TH>
                        <TH className="w-20 text-center">ISR</TH>
                      </>
                    )}
                    <TH className="w-24 text-right">Prioridad</TH>
                    <TH className="w-32">Cuenta</TH>
                    <TH className="w-28">Estado</TH>
                  </tr>
                </THead>
                <TBody>
                  {rows.map((c) => (
                    <TR
                      key={c.id}
                      className={canEdit ? 'cursor-pointer' : undefined}
                      onClick={() => canEdit && setEditing(c)}
                    >
                      <TD>
                        <p className="font-medium">{c.name}</p>
                        <p className="text-muted-foreground font-mono text-xs">
                          {c.code}
                          {c.is_legal_order && ' · orden judicial'}
                        </p>
                      </TD>
                      {kind === 'earning' && (
                        <>
                          <TD className="text-center">{flag(!!c.taxable_css)}</TD>
                          <TD className="text-center">{flag(!!c.taxable_se)}</TD>
                          <TD className="text-center">{flag(!!c.taxable_isr)}</TD>
                        </>
                      )}
                      <TD className="text-right tabular-nums">{c.priority}</TD>
                      <TD className="font-mono text-xs">{c.accounting_account || '—'}</TD>
                      <TD>
                        <Badge variant={c.is_active ? 'success' : 'neutral'}>
                          {c.is_active ? 'Activo' : 'Inactivo'}
                        </Badge>
                      </TD>
                    </TR>
                  ))}
                </TBody>
              </Table>
            </section>
          )
        })
      )}
      {editing && (
        <ConceptDialog
          concept={editing === 'new' ? undefined : editing}
          onClose={() => setEditing(null)}
        />
      )}
    </div>
  )
}
