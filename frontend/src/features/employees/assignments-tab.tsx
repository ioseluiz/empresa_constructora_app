import { useQueryClient } from '@tanstack/react-query'
import { HardHat, Plus, Trash2 } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import type { Employee, ProjectAssignment } from '@/api/generated/model'
import { useOrgPositionsList } from '@/api/generated/organizacion/organizacion'
import {
  getHrAssignmentsListQueryKey,
  getHrEmployeesListQueryKey,
  getHrEmployeesRetrieveQueryKey,
  useHrAssignmentsCreate,
  useHrAssignmentsDestroy,
  useHrAssignmentsList,
  useHrAssignmentsPartialUpdate,
} from '@/api/generated/personal/personal'
import { useProjectsList } from '@/api/generated/proyectos/proyectos'
import { Alert } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Dialog } from '@/components/ui/dialog'
import { FormField } from '@/components/ui/form-field'
import { Input } from '@/components/ui/input'
import { EmptyState, LoadingBlock } from '@/components/ui/page'
import { Select } from '@/components/ui/select'
import { Table, TBody, TD, TH, THead, TR } from '@/components/ui/table'
import { useAccess } from '@/features/access/use-access'
import { formatDate } from '@/lib/format'
import { useFormErrors } from '@/lib/use-form-errors'
import { todayISO } from './constants'

function AssignmentDialog({
  employee,
  assignment,
  onClose,
  onSaved,
}: {
  employee: Employee
  assignment?: ProjectAssignment
  onClose: () => void
  onSaved: () => void
}) {
  const projects = useProjectsList({ ordering: 'code' })
  const positions = useOrgPositionsList()
  const [form, setForm] = useState({
    project: assignment?.project ?? '',
    position: assignment?.position ?? '',
    start_date: assignment?.start_date ?? todayISO(),
    end_date: assignment?.end_date ?? '',
    notes: assignment?.notes ?? '',
  })
  const { errors, error, reset, handle } = useFormErrors()
  const done = () => {
    onSaved()
    onClose()
  }
  const create = useHrAssignmentsCreate({ mutation: { onSuccess: done, onError: handle } })
  const update = useHrAssignmentsPartialUpdate({ mutation: { onSuccess: done, onError: handle } })
  const submit = (e: FormEvent) => {
    e.preventDefault()
    reset()
    const data = {
      ...form,
      employee: employee.id,
      position: form.position || null,
      end_date: form.end_date || null,
    }
    if (assignment) update.mutate({ id: assignment.id, data })
    else create.mutate({ data })
  }
  const set =
    (key: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
      setForm({ ...form, [key]: e.target.value })

  return (
    <Dialog
      open
      onOpenChange={(o) => !o && onClose()}
      title={assignment ? 'Editar asignación' : 'Asignar a proyecto'}
      description="Los roles limitados a ese proyecto (jefe de proyecto, supervisor) verán a este empleado."
      footer={
        <>
          <Button variant="outline" onClick={onClose}>
            Cancelar
          </Button>
          <Button
            type="submit"
            form="assignment-form"
            loading={create.isPending || update.isPending}
          >
            Guardar
          </Button>
        </>
      }
    >
      <form id="assignment-form" onSubmit={submit} className="space-y-4">
        {error && <Alert>{error}</Alert>}
        <FormField id="asg-project" label="Proyecto" error={errors.project}>
          <Select
            id="asg-project"
            className="w-full"
            required
            disabled={!!assignment}
            value={form.project}
            onChange={set('project')}
          >
            <option value="">Selecciona…</option>
            {projects.data?.results
              .filter((p) => p.status !== 'finished' || p.id === form.project)
              .map((p) => (
                <option key={p.id} value={p.id}>
                  {p.code} · {p.name}
                </option>
              ))}
          </Select>
        </FormField>
        <FormField id="asg-position" label="Puesto en la obra (opcional)" error={errors.position}>
          <Select
            id="asg-position"
            className="w-full"
            value={form.position}
            onChange={set('position')}
          >
            <option value="">El de su contrato</option>
            {positions.data?.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </Select>
        </FormField>
        <div className="grid gap-4 sm:grid-cols-2">
          <FormField id="asg-start" label="Desde" error={errors.start_date}>
            <Input
              id="asg-start"
              type="date"
              required
              value={form.start_date}
              onChange={set('start_date')}
            />
          </FormField>
          <FormField id="asg-end" label="Hasta (opcional)" error={errors.end_date}>
            <Input id="asg-end" type="date" value={form.end_date} onChange={set('end_date')} />
          </FormField>
        </div>
        <FormField id="asg-notes" label="Observaciones" error={errors.notes}>
          <Input id="asg-notes" value={form.notes} onChange={set('notes')} />
        </FormField>
      </form>
    </Dialog>
  )
}

export function AssignmentsTab({ employee }: { employee: Employee }) {
  const queryClient = useQueryClient()
  const { can } = useAccess()
  const canManage = can('hr.employee.manage')
  const [editing, setEditing] = useState<ProjectAssignment | 'new' | null>(null)
  const [confirmDelete, setConfirmDelete] = useState<ProjectAssignment | null>(null)
  const assignments = useHrAssignmentsList({ employee: employee.id })
  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: getHrAssignmentsListQueryKey() })
    void queryClient.invalidateQueries({ queryKey: getHrEmployeesListQueryKey() })
    void queryClient.invalidateQueries({ queryKey: getHrEmployeesRetrieveQueryKey(employee.id) })
  }
  const destroy = useHrAssignmentsDestroy({
    mutation: {
      onSuccess: () => {
        invalidate()
        setConfirmDelete(null)
      },
    },
  })
  const today = todayISO()
  const rows = assignments.data ?? []

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-4">
        <p className="text-muted-foreground text-sm">
          Obras donde trabaja o trabajó. Las horas por proyecto se tomarán de las marcaciones.
        </p>
        {canManage && employee.status === 'active' && (
          <Button onClick={() => setEditing('new')}>
            <Plus className="size-4" /> Asignar a proyecto
          </Button>
        )}
      </div>
      {assignments.isPending ? (
        <LoadingBlock />
      ) : rows.length === 0 ? (
        <EmptyState
          icon={HardHat}
          title="Sin asignaciones"
          description="Sin proyecto asignado, su planilla se carga a la oficina central."
        />
      ) : (
        <Table>
          <THead>
            <tr>
              <TH>Proyecto</TH>
              <TH>Puesto</TH>
              <TH>Desde</TH>
              <TH>Hasta</TH>
              <TH>Estado</TH>
              {canManage && <TH className="w-24" />}
            </tr>
          </THead>
          <TBody>
            {rows.map((a) => {
              const current = a.start_date <= today && (!a.end_date || a.end_date >= today)
              return (
                <TR key={a.id}>
                  <TD>
                    <span className="text-muted-foreground font-mono text-xs">
                      {a.project_ref.code}
                    </span>{' '}
                    {a.project_ref.name}
                    {a.notes && <p className="text-muted-foreground text-xs">{a.notes}</p>}
                  </TD>
                  <TD className="text-muted-foreground">{a.position_name ?? 'Según contrato'}</TD>
                  <TD className="whitespace-nowrap">{formatDate(a.start_date)}</TD>
                  <TD className="whitespace-nowrap">{a.end_date ? formatDate(a.end_date) : '—'}</TD>
                  <TD>
                    <Badge variant={current ? 'success' : 'neutral'}>
                      {current ? 'Actual' : a.start_date > today ? 'Programada' : 'Finalizada'}
                    </Badge>
                  </TD>
                  {canManage && (
                    <TD className="text-right whitespace-nowrap">
                      <Button size="sm" variant="ghost" onClick={() => setEditing(a)}>
                        Editar
                      </Button>
                      <Button
                        size="icon"
                        variant="ghost"
                        aria-label="Eliminar asignación"
                        onClick={() => setConfirmDelete(a)}
                      >
                        <Trash2 className="size-4" />
                      </Button>
                    </TD>
                  )}
                </TR>
              )
            })}
          </TBody>
        </Table>
      )}
      {editing && (
        <AssignmentDialog
          employee={employee}
          assignment={editing === 'new' ? undefined : editing}
          onClose={() => setEditing(null)}
          onSaved={invalidate}
        />
      )}
      {confirmDelete && (
        <Dialog
          open
          onOpenChange={(o) => !o && setConfirmDelete(null)}
          title="Eliminar asignación"
          description={`Se eliminará la asignación a ${confirmDelete.project_ref.code}. Si el empleado dejó la obra, es mejor indicar la fecha "Hasta" para conservar el historial.`}
          footer={
            <>
              <Button variant="outline" onClick={() => setConfirmDelete(null)}>
                Cancelar
              </Button>
              <Button
                variant="danger"
                loading={destroy.isPending}
                onClick={() => destroy.mutate({ id: confirmDelete.id })}
              >
                Eliminar
              </Button>
            </>
          }
        />
      )}
    </div>
  )
}
