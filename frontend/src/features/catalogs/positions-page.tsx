import { useQueryClient } from '@tanstack/react-query'
import { Plus } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import type { Position } from '@/api/generated/model'
import {
  getOrgPositionsListQueryKey,
  useOrgCbaCategoriesList,
  useOrgPositionsCreate,
  useOrgPositionsList,
  useOrgPositionsPartialUpdate,
} from '@/api/generated/organizacion/organizacion'
import { Alert } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Switch } from '@/components/ui/checkbox'
import { Dialog } from '@/components/ui/dialog'
import { FormField } from '@/components/ui/form-field'
import { Input } from '@/components/ui/input'
import { LoadingBlock, PageHeader } from '@/components/ui/page'
import { Select } from '@/components/ui/select'
import { Table, TBody, TD, TH, THead, TR } from '@/components/ui/table'
import { useFormErrors } from './use-mutation-feedback'

function PositionDialog({ position, onClose }: { position?: Position; onClose: () => void }) {
  const queryClient = useQueryClient()
  const categories = useOrgCbaCategoriesList()
  const [form, setForm] = useState({
    code: position?.code ?? '',
    name: position?.name ?? '',
    area: position?.area ?? 'field',
    cba_category: position?.cba_category ?? '',
    description: position?.description ?? '',
    is_active: position?.is_active ?? true,
  })
  const { errors, error, reset, handle } = useFormErrors()
  const onSuccess = () => {
    void queryClient.invalidateQueries({ queryKey: getOrgPositionsListQueryKey() })
    onClose()
  }
  const create = useOrgPositionsCreate({ mutation: { onSuccess, onError: handle } })
  const update = useOrgPositionsPartialUpdate({ mutation: { onSuccess, onError: handle } })
  const submit = (e: FormEvent) => {
    e.preventDefault()
    reset()
    const data = {
      ...form,
      area: form.area as Position['area'],
      cba_category: form.cba_category || null,
    }
    if (position) update.mutate({ id: position.id, data })
    else create.mutate({ data })
  }
  const set =
    (key: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
      setForm({ ...form, [key]: e.target.value })

  return (
    <Dialog
      open
      onOpenChange={(o) => !o && onClose()}
      title={position ? `Editar ${position.name}` : 'Nuevo puesto'}
      footer={
        <Button type="submit" form="pos-form" loading={create.isPending || update.isPending}>
          Guardar
        </Button>
      }
    >
      <form id="pos-form" onSubmit={submit} className="space-y-4">
        {error && <Alert>{error}</Alert>}
        <div className="grid gap-4 sm:grid-cols-[8rem_1fr]">
          <FormField id="pos-code" label="Código" error={errors.code}>
            <Input id="pos-code" required value={form.code} onChange={set('code')} />
          </FormField>
          <FormField id="pos-name" label="Nombre" error={errors.name}>
            <Input id="pos-name" required value={form.name} onChange={set('name')} />
          </FormField>
        </div>
        <FormField id="pos-area" label="Área">
          <Select id="pos-area" className="w-full" value={form.area} onChange={set('area')}>
            <option value="field">Obra</option>
            <option value="office">Oficina</option>
          </Select>
        </FormField>
        <FormField
          id="pos-cba"
          label="Categoría de la convención"
          error={errors.cba_category}
          hint={
            <span className="text-muted-foreground text-xs">Define la tarifa mínima por hora</span>
          }
        >
          <Select
            id="pos-cba"
            className="w-full"
            value={form.cba_category}
            onChange={set('cba_category')}
          >
            <option value="">— No aplica —</option>
            {categories.data?.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField id="pos-desc" label="Descripción">
          <Input id="pos-desc" value={form.description} onChange={set('description')} />
        </FormField>
        {position && (
          <label className="flex items-center justify-between text-sm font-medium">
            Activo
            <Switch
              checked={form.is_active}
              onCheckedChange={(v) => setForm({ ...form, is_active: v })}
            />
          </label>
        )}
      </form>
    </Dialog>
  )
}

export function PositionsPage() {
  const positions = useOrgPositionsList()
  const [editing, setEditing] = useState<Position | 'new' | null>(null)
  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <PageHeader
        title="Puestos"
        description="Cargos de obra y de oficina. Los de obra pueden vincularse a la convención."
        actions={
          <Button onClick={() => setEditing('new')}>
            <Plus className="size-4" /> Nuevo puesto
          </Button>
        }
      />
      {positions.isPending ? (
        <LoadingBlock />
      ) : (
        <Table>
          <THead>
            <tr>
              <TH>Puesto</TH>
              <TH>Área</TH>
              <TH>Categoría de convención</TH>
              <TH>Estado</TH>
            </tr>
          </THead>
          <TBody>
            {positions.data?.map((p) => (
              <TR key={p.id} className="cursor-pointer" onClick={() => setEditing(p)}>
                <TD>
                  <span className="text-muted-foreground font-mono text-xs">{p.code}</span> {p.name}
                </TD>
                <TD>{p.area_display}</TD>
                <TD className="text-muted-foreground">{p.cba_category_name ?? '—'}</TD>
                <TD>
                  <Badge variant={p.is_active ? 'success' : 'neutral'}>
                    {p.is_active ? 'Activo' : 'Inactivo'}
                  </Badge>
                </TD>
              </TR>
            ))}
          </TBody>
        </Table>
      )}
      {editing && (
        <PositionDialog
          key={editing === 'new' ? 'new' : editing.id}
          position={editing === 'new' ? undefined : editing}
          onClose={() => setEditing(null)}
        />
      )}
    </div>
  )
}
