import { useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, History, Plus } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import type { CBACategory } from '@/api/generated/model'
import {
  getOrgCbaCategoriesListQueryKey,
  getOrgCbaRatesListQueryKey,
  useOrgCbaCategoriesCreate,
  useOrgCbaCategoriesList,
  useOrgCbaRatesCreate,
  useOrgCbaRatesList,
} from '@/api/generated/organizacion/organizacion'
import { useTenantCurrentRetrieve } from '@/api/generated/empresa/empresa'
import { Alert } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Dialog } from '@/components/ui/dialog'
import { FormField } from '@/components/ui/form-field'
import { Input } from '@/components/ui/input'
import { LoadingBlock, PageHeader } from '@/components/ui/page'
import { Table, TBody, TD, TH, THead, TR } from '@/components/ui/table'
import { formatDate, formatMoney } from '@/lib/format'
import { useFormErrors } from './use-mutation-feedback'

function RatesDialog({ category, onClose }: { category: CBACategory; onClose: () => void }) {
  const queryClient = useQueryClient()
  const rates = useOrgCbaRatesList({ category: category.id })
  const [form, setForm] = useState({ hourly_rate: '', valid_from: '', source: '' })
  const { errors, error, reset, handle } = useFormErrors()
  const create = useOrgCbaRatesCreate({
    mutation: {
      onSuccess: () => {
        void queryClient.invalidateQueries({ queryKey: getOrgCbaRatesListQueryKey() })
        void queryClient.invalidateQueries({ queryKey: getOrgCbaCategoriesListQueryKey() })
        setForm({ hourly_rate: '', valid_from: '', source: '' })
      },
      onError: handle,
    },
  })
  const submit = (e: FormEvent) => {
    e.preventDefault()
    reset()
    create.mutate({ data: { ...form, category: category.id } })
  }
  return (
    <Dialog
      open
      size="lg"
      onOpenChange={(o) => !o && onClose()}
      title={`Tarifas · ${category.name}`}
      description="Cada tarifa rige desde su fecha hasta que empiece la siguiente."
    >
      <div className="space-y-5">
        <form onSubmit={submit} className="space-y-3 rounded-md border p-4">
          <p className="text-sm font-medium">Nueva tarifa</p>
          {error && <Alert>{error}</Alert>}
          <div className="grid gap-3 sm:grid-cols-3">
            <FormField id="rate-amount" label="Tarifa por hora (B/.)" error={errors.hourly_rate}>
              <Input
                id="rate-amount"
                type="number"
                step="0.0001"
                min="0.0001"
                required
                value={form.hourly_rate}
                onChange={(e) => setForm({ ...form, hourly_rate: e.target.value })}
              />
            </FormField>
            <FormField id="rate-from" label="Vigente desde" error={errors.valid_from}>
              <Input
                id="rate-from"
                type="date"
                required
                value={form.valid_from}
                onChange={(e) => setForm({ ...form, valid_from: e.target.value })}
              />
            </FormField>
            <FormField id="rate-source" label="Fuente">
              <Input
                id="rate-source"
                placeholder="Convención 2026-2029"
                value={form.source}
                onChange={(e) => setForm({ ...form, source: e.target.value })}
              />
            </FormField>
          </div>
          <div className="flex justify-end">
            <Button type="submit" size="sm" loading={create.isPending}>
              Agregar tarifa
            </Button>
          </div>
        </form>
        {rates.isPending ? (
          <LoadingBlock />
        ) : rates.data?.length ? (
          <Table>
            <THead>
              <tr>
                <TH>Vigente desde</TH>
                <TH className="text-right">Tarifa por hora</TH>
                <TH>Fuente</TH>
              </tr>
            </THead>
            <TBody>
              {rates.data.map((r) => (
                <TR key={r.id}>
                  <TD>{formatDate(r.valid_from)}</TD>
                  <TD className="text-right tabular-nums">{formatMoney(r.hourly_rate, 4)}</TD>
                  <TD className="text-muted-foreground">{r.source || '—'}</TD>
                </TR>
              ))}
            </TBody>
          </Table>
        ) : (
          <p className="text-muted-foreground text-center text-sm">Sin tarifas registradas.</p>
        )}
      </div>
    </Dialog>
  )
}

function NewCategoryDialog({ onClose }: { onClose: () => void }) {
  const queryClient = useQueryClient()
  const [form, setForm] = useState({ code: '', name: '' })
  const { errors, error, reset, handle } = useFormErrors()
  const create = useOrgCbaCategoriesCreate({
    mutation: {
      onSuccess: () => {
        void queryClient.invalidateQueries({ queryKey: getOrgCbaCategoriesListQueryKey() })
        onClose()
      },
      onError: handle,
    },
  })
  return (
    <Dialog
      open
      onOpenChange={(o) => !o && onClose()}
      title="Nueva categoría"
      footer={
        <Button type="submit" form="cat-form" loading={create.isPending}>
          Guardar
        </Button>
      }
    >
      <form
        id="cat-form"
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault()
          reset()
          create.mutate({ data: form })
        }}
      >
        {error && <Alert>{error}</Alert>}
        <FormField id="cat-code" label="Código" error={errors.code}>
          <Input
            id="cat-code"
            required
            value={form.code}
            onChange={(e) => setForm({ ...form, code: e.target.value })}
          />
        </FormField>
        <FormField id="cat-name" label="Nombre" error={errors.name}>
          <Input
            id="cat-name"
            required
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
          />
        </FormField>
      </form>
    </Dialog>
  )
}

export function CbaPage() {
  const categories = useOrgCbaCategoriesList()
  const tenant = useTenantCurrentRetrieve()
  const [selected, setSelected] = useState<CBACategory | null>(null)
  const [creating, setCreating] = useState(false)
  const missing = categories.data?.filter((c) => c.is_active && !c.current_rate).length ?? 0

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <PageHeader
        title="Convención SUNTRACS–CAPAC"
        description="Categorías de la convención colectiva de la construcción y sus tarifas por hora."
        actions={
          <Button onClick={() => setCreating(true)}>
            <Plus className="size-4" /> Nueva categoría
          </Button>
        }
      />
      {tenant.data && !tenant.data.applies_cba && (
        <Alert>
          La empresa tiene desactivada la convención (Configuración → Empresa). Las tarifas no se
          aplicarán.
        </Alert>
      )}
      {missing > 0 && (
        <div className="border-accent/40 bg-accent/10 flex items-start gap-3 rounded-md border px-4 py-3 text-sm">
          <AlertTriangle className="text-accent mt-0.5 size-4 shrink-0" />
          <span>
            {missing} {missing === 1 ? 'categoría no tiene' : 'categorías no tienen'} tarifa
            vigente. Ingresa las tarifas de la convención vigente antes de calcular planillas.
          </span>
        </div>
      )}
      {categories.isPending ? (
        <LoadingBlock />
      ) : (
        <Table>
          <THead>
            <tr>
              <TH>Categoría</TH>
              <TH className="text-right">Tarifa vigente</TH>
              <TH>Desde</TH>
              <TH className="w-28" />
            </tr>
          </THead>
          <TBody>
            {categories.data?.map((c) => (
              <TR key={c.id}>
                <TD>
                  <span className="text-muted-foreground font-mono text-xs">{c.code}</span> {c.name}
                </TD>
                <TD className="text-right tabular-nums">
                  {c.current_rate ? formatMoney(c.current_rate.hourly_rate, 4) : '—'}
                </TD>
                <TD className="text-muted-foreground">
                  {c.current_rate ? formatDate(c.current_rate.valid_from) : 'Sin tarifa'}
                </TD>
                <TD className="text-right">
                  <Button variant="ghost" size="sm" onClick={() => setSelected(c)}>
                    <History className="size-3.5" /> Tarifas
                  </Button>
                </TD>
              </TR>
            ))}
          </TBody>
        </Table>
      )}
      {selected && <RatesDialog category={selected} onClose={() => setSelected(null)} />}
      {creating && <NewCategoryDialog onClose={() => setCreating(false)} />}
    </div>
  )
}
