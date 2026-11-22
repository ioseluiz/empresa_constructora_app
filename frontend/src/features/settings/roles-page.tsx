import { useQueryClient } from '@tanstack/react-query'
import { Lock, Plus, Trash2, Users } from 'lucide-react'
import { useMemo, useState } from 'react'
import { ApiError } from '@/api/client'
import {
  getIamRolesListQueryKey,
  useIamPermissionsList,
  useIamRolesCreate,
  useIamRolesDestroy,
  useIamRolesList,
  useIamRolesPartialUpdate,
} from '@/api/generated/iam/iam'
import type { Permission, Role } from '@/api/generated/model'
import { Alert } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import { Dialog } from '@/components/ui/dialog'
import { FormField } from '@/components/ui/form-field'
import { Input } from '@/components/ui/input'
import { LoadingBlock, PageHeader } from '@/components/ui/page'

type Draft = { id?: string; name: string; description: string; permissions: string[] }

function groupByModule(perms: Permission[]) {
  const groups = new Map<string, Permission[]>()
  for (const p of perms) groups.set(p.module, [...(groups.get(p.module) ?? []), p])
  return [...groups.entries()]
}

function RoleDialog({ initial, onClose }: { initial: Draft; onClose: () => void }) {
  const queryClient = useQueryClient()
  const catalog = useIamPermissionsList()
  const [form, setForm] = useState<Draft>(initial)
  const [error, setError] = useState<string | null>(null)
  const groups = useMemo(() => groupByModule(catalog.data ?? []), [catalog.data])
  const done = () => {
    void queryClient.invalidateQueries({ queryKey: getIamRolesListQueryKey() })
    onClose()
  }
  const onError = (err: unknown) =>
    setError(err instanceof ApiError ? err.message : 'No se pudo guardar el rol.')
  const create = useIamRolesCreate({ mutation: { onSuccess: done, onError } })
  const update = useIamRolesPartialUpdate({ mutation: { onSuccess: done, onError } })

  const toggle = (codes: string[], on: boolean) =>
    setForm({
      ...form,
      permissions: on
        ? [...new Set([...form.permissions, ...codes])]
        : form.permissions.filter((c) => !codes.includes(c)),
    })
  const save = () => {
    const data = { name: form.name, description: form.description, permissions: form.permissions }
    if (form.id) update.mutate({ id: form.id, data })
    else create.mutate({ data })
  }

  return (
    <Dialog
      open
      size="lg"
      onOpenChange={(o) => !o && onClose()}
      title={form.id ? 'Editar rol' : 'Nuevo rol'}
      description="Los cambios aplican de inmediato a todos los usuarios con este rol."
      footer={
        <>
          <Button variant="outline" onClick={onClose}>
            Cancelar
          </Button>
          <Button onClick={save} loading={create.isPending || update.isPending}>
            Guardar
          </Button>
        </>
      }
    >
      <div className="space-y-5">
        {error && <Alert>{error}</Alert>}
        <div className="grid gap-4 sm:grid-cols-2">
          <FormField id="role-name" label="Nombre">
            <Input
              id="role-name"
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
            />
          </FormField>
          <FormField id="role-desc" label="Descripción">
            <Input
              id="role-desc"
              value={form.description}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
            />
          </FormField>
        </div>
        {catalog.isPending ? (
          <LoadingBlock />
        ) : (
          <div className="space-y-4">
            {groups.map(([module, perms]) => {
              const codes = perms.map((p) => p.code)
              const all = codes.every((c) => form.permissions.includes(c))
              return (
                <fieldset key={module} className="rounded-md border">
                  <legend className="sr-only">{module}</legend>
                  <label className="bg-muted/50 flex items-center gap-3 border-b px-3 py-2 text-sm font-medium">
                    <Checkbox checked={all} onChange={(e) => toggle(codes, e.target.checked)} />
                    {module}
                  </label>
                  <div className="grid gap-x-4 p-2 sm:grid-cols-2">
                    {perms.map((p) => (
                      <label
                        key={p.code}
                        className="hover:bg-muted flex cursor-pointer items-start gap-3 rounded px-2 py-1.5 text-sm"
                      >
                        <Checkbox
                          className="mt-0.5"
                          checked={form.permissions.includes(p.code)}
                          onChange={(e) => toggle([p.code], e.target.checked)}
                        />
                        {p.label}
                      </label>
                    ))}
                  </div>
                </fieldset>
              )
            })}
          </div>
        )}
      </div>
    </Dialog>
  )
}

export function RolesPage() {
  const queryClient = useQueryClient()
  const roles = useIamRolesList()
  const [draft, setDraft] = useState<Draft | null>(null)
  const [error, setError] = useState<string | null>(null)
  const destroy = useIamRolesDestroy({
    mutation: {
      onSuccess: () => void queryClient.invalidateQueries({ queryKey: getIamRolesListQueryKey() }),
      onError: (err) => setError(err instanceof ApiError ? err.message : 'No se pudo eliminar.'),
    },
  })
  const edit = (role: Role) =>
    setDraft({
      id: role.id,
      name: role.name,
      description: role.description ?? '',
      permissions: role.permissions ?? [],
    })

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <PageHeader
        title="Roles"
        description="Define qué puede hacer cada tipo de usuario. Un usuario puede tener varios roles."
        actions={
          <Button onClick={() => setDraft({ name: '', description: '', permissions: [] })}>
            <Plus className="size-4" /> Nuevo rol
          </Button>
        }
      />
      {error && <Alert>{error}</Alert>}
      {roles.isPending ? (
        <LoadingBlock />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {roles.data?.map((role) => (
            <Card key={role.id} className="flex flex-col p-5">
              <div className="flex items-start justify-between gap-2">
                <h3 className="font-semibold">{role.name}</h3>
                {role.is_system && (
                  <Badge>
                    <Lock className="size-3" /> Plantilla
                  </Badge>
                )}
              </div>
              <p className="text-muted-foreground mt-1 flex-1 text-sm">{role.description}</p>
              <div className="mt-4 flex items-center justify-between">
                <span className="text-muted-foreground flex items-center gap-3 text-xs">
                  <span className="flex items-center gap-1">
                    <Users className="size-3.5" /> {role.member_count}
                  </span>
                  <span>{role.permissions?.length ?? 0} permisos</span>
                </span>
                <span className="flex gap-1">
                  <Button variant="ghost" size="sm" onClick={() => edit(role)}>
                    Editar
                  </Button>
                  {role.member_count === 0 && (
                    <Button
                      variant="ghost"
                      size="icon"
                      aria-label={`Eliminar ${role.name}`}
                      onClick={() => destroy.mutate({ id: role.id })}
                    >
                      <Trash2 className="size-4" />
                    </Button>
                  )}
                </span>
              </div>
            </Card>
          ))}
        </div>
      )}
      {draft && (
        <RoleDialog key={draft.id ?? 'nuevo'} initial={draft} onClose={() => setDraft(null)} />
      )}
    </div>
  )
}
