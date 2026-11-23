import { useQueryClient } from '@tanstack/react-query'
import { Building, FolderTree, HardHat, Plus } from 'lucide-react'
import { useMemo, useState, type FormEvent } from 'react'
import type { CostCenter } from '@/api/generated/model'
import {
  getOrgCostCentersListQueryKey,
  useOrgCostCentersCreate,
  useOrgCostCentersList,
  useOrgCostCentersPartialUpdate,
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
import { useFormErrors } from '@/lib/use-form-errors'

/** Ordena en profundidad para mostrar el árbol con sangría. */
function flattenTree(items: CostCenter[]) {
  const children = new Map<string | null, CostCenter[]>()
  for (const c of items) {
    const key = c.parent ?? null
    children.set(key, [...(children.get(key) ?? []), c])
  }
  const out: { node: CostCenter; depth: number }[] = []
  const walk = (parent: string | null, depth: number) => {
    for (const node of children.get(parent) ?? []) {
      out.push({ node, depth })
      walk(node.id, depth + 1)
    }
  }
  walk(null, 0)
  return out
}

const KIND_ICON = { office: Building, project: HardHat, area: FolderTree }

function CostCenterDialog({
  center,
  all,
  onClose,
}: {
  center?: CostCenter
  all: CostCenter[]
  onClose: () => void
}) {
  const queryClient = useQueryClient()
  const [form, setForm] = useState({
    code: center?.code ?? '',
    name: center?.name ?? '',
    parent: center?.parent ?? '',
    is_active: center?.is_active ?? true,
  })
  const { errors, error, reset, handle } = useFormErrors()
  const onSuccess = () => {
    void queryClient.invalidateQueries({ queryKey: getOrgCostCentersListQueryKey() })
    onClose()
  }
  const create = useOrgCostCentersCreate({ mutation: { onSuccess, onError: handle } })
  const update = useOrgCostCentersPartialUpdate({ mutation: { onSuccess, onError: handle } })
  const submit = (e: FormEvent) => {
    e.preventDefault()
    reset()
    const data = { ...form, parent: form.parent || null }
    if (center) update.mutate({ id: center.id, data })
    else create.mutate({ data: { ...data, kind: 'area' } })
  }
  return (
    <Dialog
      open
      onOpenChange={(o) => !o && onClose()}
      title={center ? `Editar ${center.code}` : 'Nuevo centro de costo'}
      description="Áreas de la oficina o fases de un proyecto (p. ej. Estructura, Acabados)."
      footer={
        <Button type="submit" form="cc-form" loading={create.isPending || update.isPending}>
          Guardar
        </Button>
      }
    >
      <form id="cc-form" onSubmit={submit} className="space-y-4">
        {error && <Alert>{error}</Alert>}
        <FormField id="cc-code" label="Código" error={errors.code}>
          <Input
            id="cc-code"
            required
            value={form.code}
            onChange={(e) => setForm({ ...form, code: e.target.value })}
          />
        </FormField>
        <FormField id="cc-name" label="Nombre" error={errors.name}>
          <Input
            id="cc-name"
            required
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
          />
        </FormField>
        <FormField id="cc-parent" label="Pertenece a" error={errors.parent}>
          <Select
            id="cc-parent"
            className="w-full"
            value={form.parent}
            onChange={(e) => setForm({ ...form, parent: e.target.value })}
          >
            <option value="">— Nivel superior —</option>
            {all
              .filter((c) => c.id !== center?.id)
              .map((c) => (
                <option key={c.id} value={c.id}>
                  {c.code} · {c.name}
                </option>
              ))}
          </Select>
        </FormField>
        {center && (
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

export function CostCentersPage() {
  const centers = useOrgCostCentersList()
  const [editing, setEditing] = useState<CostCenter | 'new' | null>(null)
  const tree = useMemo(() => flattenTree(centers.data ?? []), [centers.data])

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <PageHeader
        title="Centros de costo"
        description="A cada centro de costo se imputan la planilla y, en el futuro, los demás gastos."
        actions={
          <Button onClick={() => setEditing('new')}>
            <Plus className="size-4" /> Nuevo centro de costo
          </Button>
        }
      />
      {centers.isPending ? (
        <LoadingBlock />
      ) : (
        <Table>
          <THead>
            <tr>
              <TH>Centro de costo</TH>
              <TH>Tipo</TH>
              <TH>Estado</TH>
            </tr>
          </THead>
          <TBody>
            {tree.map(({ node, depth }) => {
              const Icon = KIND_ICON[node.kind as keyof typeof KIND_ICON] ?? FolderTree
              const editable = node.kind !== 'project'
              return (
                <TR
                  key={node.id}
                  className={editable ? 'cursor-pointer' : undefined}
                  onClick={() => editable && setEditing(node)}
                  title={editable ? undefined : 'Se edita desde Proyectos'}
                >
                  <TD>
                    <span className="flex items-center gap-2" style={{ paddingLeft: depth * 20 }}>
                      <Icon className="text-muted-foreground size-4" />
                      <span className="text-muted-foreground font-mono text-xs">{node.code}</span>
                      {node.name}
                    </span>
                  </TD>
                  <TD className="text-muted-foreground">{node.kind_display}</TD>
                  <TD>
                    <Badge variant={node.is_active ? 'success' : 'neutral'}>
                      {node.is_active ? 'Activo' : 'Inactivo'}
                    </Badge>
                  </TD>
                </TR>
              )
            })}
          </TBody>
        </Table>
      )}
      {editing && (
        <CostCenterDialog
          key={editing === 'new' ? 'new' : editing.id}
          center={editing === 'new' ? undefined : editing}
          all={centers.data ?? []}
          onClose={() => setEditing(null)}
        />
      )}
    </div>
  )
}
