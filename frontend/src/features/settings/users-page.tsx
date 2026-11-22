import { useQueryClient } from '@tanstack/react-query'
import { Mail, MoreHorizontal, RotateCw, ShieldCheck, UserPlus, Users, X } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { ApiError } from '@/api/client'
import {
  getIamInvitationsListQueryKey,
  getIamMembersListQueryKey,
  useIamInvitationsCreate,
  useIamInvitationsDestroy,
  useIamInvitationsList,
  useIamInvitationsResendCreate,
  useIamMembersList,
  useIamMembersPartialUpdate,
  useIamRolesList,
} from '@/api/generated/iam/iam'
import type { Member, PatchedMemberRequest } from '@/api/generated/model'
import { useProjectsList } from '@/api/generated/proyectos/proyectos'
import { Alert } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Dialog } from '@/components/ui/dialog'
import { FormField } from '@/components/ui/form-field'
import { Input } from '@/components/ui/input'
import { EmptyState, LoadingBlock, PageHeader } from '@/components/ui/page'
import { formatDateTime } from '@/lib/format'
import { Table, TBody, TD, TH, THead, TR } from '@/components/ui/table'
import { useAccess } from '@/features/access/use-access'
import { useAuth } from '@/features/auth/use-auth'
import { AssignmentEditor, type AssignmentDraft } from './assignment-editor'
import { RolePicker } from './role-picker'

function errorMessage(err: unknown) {
  return err instanceof ApiError ? err.message : 'No se pudo completar la acción.'
}

function InviteDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const queryClient = useQueryClient()
  const roles = useIamRolesList()
  const [email, setEmail] = useState('')
  const [roleIds, setRoleIds] = useState<string[]>([])
  const [error, setError] = useState<string | null>(null)
  const invite = useIamInvitationsCreate({
    mutation: {
      onSuccess: () => {
        void queryClient.invalidateQueries({ queryKey: getIamInvitationsListQueryKey() })
        setEmail('')
        setRoleIds([])
        onClose()
      },
      onError: (err) => setError(errorMessage(err)),
    },
  })

  const submit = (e: FormEvent) => {
    e.preventDefault()
    setError(null)
    if (roleIds.length === 0) return setError('Selecciona al menos un rol.')
    invite.mutate({ data: { email, role_ids: roleIds } })
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(o) => !o && onClose()}
      title="Invitar usuario"
      description="Recibirá un correo para crear su cuenta o unirse con la que ya tiene."
      footer={
        <>
          <Button variant="outline" onClick={onClose}>
            Cancelar
          </Button>
          <Button type="submit" form="invite-form" loading={invite.isPending}>
            Enviar invitación
          </Button>
        </>
      }
    >
      <form id="invite-form" onSubmit={submit} className="space-y-5">
        {error && <Alert>{error}</Alert>}
        <FormField id="invite-email" label="Correo electrónico">
          <Input
            id="invite-email"
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="nombre@empresa.com"
          />
        </FormField>
        {roles.data ? (
          <RolePicker roles={roles.data} value={roleIds} onChange={setRoleIds} />
        ) : (
          <LoadingBlock />
        )}
      </form>
    </Dialog>
  )
}

function EditMemberDialog({ member, onClose }: { member: Member; onClose: () => void }) {
  const queryClient = useQueryClient()
  const roles = useIamRolesList()
  const projects = useProjectsList({ ordering: 'code' })
  const [draft, setDraft] = useState<AssignmentDraft>(() =>
    Object.fromEntries(
      member.assignments.map((a) => [
        a.role.id,
        { scoped: a.projects.length > 0, projects: a.projects.map((p) => p.id) },
      ]),
    ),
  )
  const [error, setError] = useState<string | null>(null)
  const update = useIamMembersPartialUpdate({
    mutation: {
      onSuccess: () => {
        void queryClient.invalidateQueries({ queryKey: getIamMembersListQueryKey() })
        onClose()
      },
      onError: (err) => setError(errorMessage(err)),
    },
  })
  const save = (patch: PatchedMemberRequest) => update.mutate({ id: member.id, data: patch })
  const saveRoles = () => {
    if (Object.values(draft).some((a) => a.scoped && a.projects.length === 0)) {
      setError('Hay roles limitados a proyectos sin ningún proyecto seleccionado.')
      return
    }
    setError(null)
    save({
      set_assignments: Object.entries(draft).map(([role_id, a]) => ({
        role_id,
        project_ids: a.scoped ? a.projects : [],
      })),
    })
  }

  return (
    <Dialog
      open
      size="lg"
      onOpenChange={(o) => !o && onClose()}
      title={member.user.full_name}
      description={member.user.email}
      footer={
        <>
          <Button
            variant="outline"
            className={member.is_active ? 'text-danger' : ''}
            onClick={() => save({ is_active: !member.is_active })}
            disabled={update.isPending}
          >
            {member.is_active ? 'Desactivar acceso' : 'Reactivar acceso'}
          </Button>
          <Button onClick={saveRoles} loading={update.isPending}>
            Guardar roles
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        {error && <Alert>{error}</Alert>}
        {roles.data && projects.data ? (
          <AssignmentEditor
            roles={roles.data}
            projects={projects.data.results}
            value={draft}
            onChange={setDraft}
          />
        ) : (
          <LoadingBlock />
        )}
      </div>
    </Dialog>
  )
}

function PendingInvitations({ canManage }: { canManage: boolean }) {
  const queryClient = useQueryClient()
  const invitations = useIamInvitationsList()
  const refresh = () =>
    void queryClient.invalidateQueries({ queryKey: getIamInvitationsListQueryKey() })
  const resend = useIamInvitationsResendCreate({ mutation: { onSuccess: refresh } })
  const revoke = useIamInvitationsDestroy({ mutation: { onSuccess: refresh } })
  const rows = invitations.data ?? []
  if (rows.length === 0) return null

  return (
    <section className="space-y-3">
      <h2 className="text-sm font-semibold">Invitaciones pendientes</h2>
      <Table>
        <THead>
          <tr>
            <TH>Correo</TH>
            <TH>Roles</TH>
            <TH>Vence</TH>
            {canManage && <TH className="text-right">Acciones</TH>}
          </tr>
        </THead>
        <TBody>
          {rows.map((inv) => (
            <TR key={inv.id}>
              <TD>
                <span className="flex items-center gap-2">
                  <Mail className="text-muted-foreground size-4" />
                  {inv.email}
                </span>
              </TD>
              <TD className="text-muted-foreground">{inv.roles.map((r) => r.name).join(', ')}</TD>
              <TD>
                {inv.is_expired ? (
                  <Badge variant="danger">Vencida</Badge>
                ) : (
                  formatDateTime(inv.expires_at)
                )}
              </TD>
              {canManage && (
                <TD className="text-right whitespace-nowrap">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => resend.mutate({ id: inv.id })}
                    disabled={resend.isPending}
                  >
                    <RotateCw className="size-3.5" /> Reenviar
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => revoke.mutate({ id: inv.id })}
                    disabled={revoke.isPending}
                  >
                    <X className="size-3.5" /> Revocar
                  </Button>
                </TD>
              )}
            </TR>
          ))}
        </TBody>
      </Table>
    </section>
  )
}

export function UsersPage() {
  const { can } = useAccess()
  const { user } = useAuth()
  const [search, setSearch] = useState('')
  const [inviting, setInviting] = useState(false)
  const [editing, setEditing] = useState<Member | null>(null)
  const members = useIamMembersList(search ? { search } : undefined)
  const canManage = can('users.manage')
  const rows = members.data?.results ?? []

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <PageHeader
        title="Usuarios"
        description="Personas con acceso a la empresa y sus roles."
        actions={
          canManage && (
            <Button onClick={() => setInviting(true)}>
              <UserPlus className="size-4" /> Invitar usuario
            </Button>
          )
        }
      />
      <Input
        type="search"
        placeholder="Buscar por nombre o correo…"
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        className="max-w-sm"
        aria-label="Buscar usuarios"
      />
      {members.isPending ? (
        <LoadingBlock />
      ) : rows.length === 0 ? (
        <EmptyState icon={Users} title="Sin resultados" />
      ) : (
        <Table>
          <THead>
            <tr>
              <TH>Usuario</TH>
              <TH>Roles</TH>
              <TH>Estado</TH>
              <TH>Último acceso</TH>
              {canManage && <TH className="w-12" />}
            </tr>
          </THead>
          <TBody>
            {rows.map((m) => {
              const editable = canManage && !m.is_owner && m.user.id !== user?.id
              return (
                <TR key={m.id}>
                  <TD>
                    <p className="font-medium">{m.user.full_name}</p>
                    <p className="text-muted-foreground text-xs">{m.user.email}</p>
                  </TD>
                  <TD>
                    <div className="flex flex-wrap gap-1">
                      {m.is_owner && <Badge variant="success">Administrador principal</Badge>}
                      {m.assignments.map((a) => (
                        <Badge
                          key={a.role.id}
                          title={
                            a.projects.map((p) => `${p.code} · ${p.name}`).join('\n') || undefined
                          }
                        >
                          {a.role.name}
                          {a.projects.length > 0 &&
                            ` · ${a.projects.length === 1 ? a.projects[0].code : `${a.projects.length} proyectos`}`}
                        </Badge>
                      ))}
                    </div>
                  </TD>
                  <TD>
                    <div className="flex items-center gap-2">
                      <Badge variant={m.is_active ? 'success' : 'neutral'}>
                        {m.is_active ? 'Activo' : 'Inactivo'}
                      </Badge>
                      {m.user.mfa_enabled && (
                        <ShieldCheck
                          className="text-success size-4"
                          aria-label="Verificación en dos pasos activa"
                        />
                      )}
                    </div>
                  </TD>
                  <TD className="text-muted-foreground">{formatDateTime(m.user.last_login)}</TD>
                  {canManage && (
                    <TD>
                      {editable && (
                        <Button
                          variant="ghost"
                          size="icon"
                          onClick={() => setEditing(m)}
                          aria-label={`Editar ${m.user.email}`}
                        >
                          <MoreHorizontal className="size-4" />
                        </Button>
                      )}
                    </TD>
                  )}
                </TR>
              )
            })}
          </TBody>
        </Table>
      )}
      <PendingInvitations canManage={canManage} />
      <InviteDialog open={inviting} onClose={() => setInviting(false)} />
      {editing && (
        <EditMemberDialog key={editing.id} member={editing} onClose={() => setEditing(null)} />
      )}
    </div>
  )
}
