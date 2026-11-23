import { useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import type { ManualPunchResult, Punch, ManualPunchRequest } from '@/api/generated/model'
import {
  getTimeclockPunchesListQueryKey,
  useTimeclockPunchesCorrectCreate,
  useTimeclockPunchesManualCreate,
  useTimeclockPunchesVoidCreate,
} from '@/api/generated/marcaciones/marcaciones'
import { useHrEmployeesList } from '@/api/generated/personal/personal'
import { useProjectsList } from '@/api/generated/proyectos/proyectos'
import { Alert } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Dialog } from '@/components/ui/dialog'
import { FormField } from '@/components/ui/form-field'
import { Input } from '@/components/ui/input'
import { LoadingBlock } from '@/components/ui/page'
import { Select } from '@/components/ui/select'
import { todayISO } from '@/features/employees/constants'
import { Options } from '@/features/employees/employee-dialog'
import { formatDay, formatTime, toLocalParts } from '@/lib/format'
import { useFormErrors } from '@/lib/use-form-errors'
import { DIRECTIONS } from './constants'

function useInvalidatePunches() {
  const queryClient = useQueryClient()
  return () => void queryClient.invalidateQueries({ queryKey: getTimeclockPunchesListQueryKey() })
}

function nowTime() {
  const d = new Date()
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

/** Registro manual: una hora para uno o varios empleados (cuadrilla) de un proyecto. */
export function ManualPunchDialog({ onClose }: { onClose: () => void }) {
  const invalidate = useInvalidatePunches()
  const projects = useProjectsList({ ordering: 'code', status: 'active' })
  const [form, setForm] = useState({
    project: '',
    date: todayISO(),
    time: nowTime(),
    direction: 'in',
    reason: '',
  })
  const [search, setSearch] = useState('')
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [result, setResult] = useState<ManualPunchResult | null>(null)
  const employees = useHrEmployeesList({
    status: 'active',
    project: form.project || undefined,
    search: search || undefined,
    ordering: 'last_name',
  })
  const rows = employees.data?.results ?? []
  const { errors, error, reset, handle } = useFormErrors()
  const create = useTimeclockPunchesManualCreate({
    mutation: {
      onSuccess: (data) => {
        invalidate()
        setResult(data)
      },
      onError: handle,
    },
  })
  const toggle = (id: string) => {
    const next = new Set(selected)
    if (next.has(id)) next.delete(id)
    else next.add(id)
    setSelected(next)
  }
  const allSelected = rows.length > 0 && rows.every((e) => selected.has(e.id))
  const submit = (e: FormEvent) => {
    e.preventDefault()
    reset()
    const data: ManualPunchRequest = {
      employees: [...selected],
      date: form.date,
      time: form.time,
      direction: form.direction as ManualPunchRequest['direction'],
      project: form.project || null,
      reason: form.reason,
    }
    create.mutate({ data })
  }

  if (result)
    return (
      <Dialog
        open
        onOpenChange={(o) => !o && onClose()}
        title="Marcaciones registradas"
        footer={<Button onClick={onClose}>Listo</Button>}
      >
        <div className="space-y-3 text-sm">
          <p>
            Se registraron <strong>{result.created.length}</strong> marcaciones.
          </p>
          {result.skipped.length > 0 && (
            <Alert>
              Ya tenían una marcación a esa hora (se omitieron): {result.skipped.join(', ')}.
            </Alert>
          )}
        </div>
      </Dialog>
    )

  return (
    <Dialog
      open
      size="lg"
      onOpenChange={(o) => !o && onClose()}
      title="Registro manual de marcaciones"
      description="Para obras sin reloj: registra la misma hora a toda la cuadrilla. Queda identificado como manual y en la bitácora."
      footer={
        <>
          <Button variant="outline" onClick={onClose}>
            Cancelar
          </Button>
          <Button
            type="submit"
            form="manual-form"
            loading={create.isPending}
            disabled={selected.size === 0}
          >
            Registrar {selected.size > 0 ? `(${selected.size})` : ''}
          </Button>
        </>
      }
    >
      <form id="manual-form" onSubmit={submit} className="space-y-4">
        {error && <Alert>{error}</Alert>}
        <div className="grid gap-4 sm:grid-cols-2">
          <FormField id="manual-project" label="Proyecto" error={errors.project}>
            <Select
              id="manual-project"
              className="w-full"
              value={form.project}
              onChange={(e) => {
                setForm({ ...form, project: e.target.value })
                setSelected(new Set())
              }}
            >
              <option value="">Oficina central / todos</option>
              {projects.data?.results.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.code} · {p.name}
                </option>
              ))}
            </Select>
          </FormField>
          <FormField id="manual-direction" label="Tipo" error={errors.direction}>
            <Select
              id="manual-direction"
              className="w-full"
              value={form.direction}
              onChange={(e) => setForm({ ...form, direction: e.target.value })}
            >
              <Options items={DIRECTIONS.slice(0, 2)} />
            </Select>
          </FormField>
          <FormField id="manual-date" label="Fecha" error={errors.date}>
            <Input
              id="manual-date"
              type="date"
              required
              max={todayISO()}
              value={form.date}
              onChange={(e) => setForm({ ...form, date: e.target.value })}
            />
          </FormField>
          <FormField id="manual-time" label="Hora" error={errors.time}>
            <Input
              id="manual-time"
              type="time"
              required
              value={form.time}
              onChange={(e) => setForm({ ...form, time: e.target.value })}
            />
          </FormField>
        </div>
        <FormField id="manual-reason" label="Motivo" error={errors.reason}>
          <Input
            id="manual-reason"
            required
            placeholder="Obra sin reloj, reloj dañado, olvido de marcación…"
            value={form.reason}
            onChange={(e) => setForm({ ...form, reason: e.target.value })}
          />
        </FormField>
        <div className="space-y-2">
          <div className="flex items-center justify-between gap-3">
            <p className="text-sm font-medium">
              Empleados{' '}
              <span className="text-muted-foreground font-normal">
                ({selected.size} seleccionados)
              </span>
            </p>
            <Input
              type="search"
              placeholder="Buscar…"
              aria-label="Buscar empleados"
              className="h-8 max-w-48"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
          {errors.employees && <p className="text-danger text-xs">{errors.employees}</p>}
          <div className="max-h-64 overflow-y-auto rounded-md border">
            {employees.isPending ? (
              <LoadingBlock />
            ) : rows.length === 0 ? (
              <p className="text-muted-foreground p-4 text-sm">
                No hay empleados activos {form.project ? 'asignados a este proyecto' : ''}.
              </p>
            ) : (
              <>
                <label className="bg-muted/50 flex items-center gap-2 border-b px-3 py-2 text-sm font-medium">
                  <Checkbox
                    checked={allSelected}
                    onChange={() => {
                      const next = new Set(selected)
                      rows.forEach((e) => (allSelected ? next.delete(e.id) : next.add(e.id)))
                      setSelected(next)
                    }}
                  />
                  Seleccionar todos
                </label>
                {rows.map((e) => (
                  <label
                    key={e.id}
                    className="hover:bg-muted/40 flex items-center gap-2 px-3 py-1.5 text-sm"
                  >
                    <Checkbox checked={selected.has(e.id)} onChange={() => toggle(e.id)} />
                    <span className="flex-1">{e.full_name}</span>
                    <span className="text-muted-foreground font-mono text-xs">{e.code}</span>
                  </label>
                ))}
              </>
            )}
          </div>
        </div>
      </form>
    </Dialog>
  )
}

export function CorrectPunchDialog({ punch, onClose }: { punch: Punch; onClose: () => void }) {
  const invalidate = useInvalidatePunches()
  const [form, setForm] = useState({
    ...toLocalParts(punch.timestamp),
    direction: punch.direction,
    reason: '',
  })
  const { errors, error, reset, handle } = useFormErrors()
  const correct = useTimeclockPunchesCorrectCreate({
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
      title={`Corregir marcación de ${punch.employee_name}`}
      description={`Original: ${formatDay(punch.timestamp)} ${formatTime(punch.timestamp)} (${punch.direction_display}). La original se conserva anulada y enlazada a la corrección.`}
      footer={
        <>
          <Button variant="outline" onClick={onClose}>
            Cancelar
          </Button>
          <Button type="submit" form="correct-form" loading={correct.isPending}>
            Guardar corrección
          </Button>
        </>
      }
    >
      <form
        id="correct-form"
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault()
          reset()
          correct.mutate({
            id: punch.id,
            data: { ...form, direction: form.direction as Punch['direction'] },
          })
        }}
      >
        {error && <Alert>{error}</Alert>}
        <div className="grid gap-4 sm:grid-cols-3">
          <FormField id="correct-date" label="Fecha" error={errors.date}>
            <Input
              id="correct-date"
              type="date"
              required
              value={form.date}
              onChange={(e) => setForm({ ...form, date: e.target.value })}
            />
          </FormField>
          <FormField id="correct-time" label="Hora" error={errors.time}>
            <Input
              id="correct-time"
              type="time"
              required
              value={form.time}
              onChange={(e) => setForm({ ...form, time: e.target.value })}
            />
          </FormField>
          <FormField id="correct-direction" label="Tipo" error={errors.direction}>
            <Select
              id="correct-direction"
              className="w-full"
              value={form.direction}
              onChange={(e) =>
                setForm({ ...form, direction: e.target.value as Punch['direction'] })
              }
            >
              <Options items={DIRECTIONS} />
            </Select>
          </FormField>
        </div>
        <FormField id="correct-reason" label="Motivo" error={errors.reason}>
          <Input
            id="correct-reason"
            required
            value={form.reason}
            onChange={(e) => setForm({ ...form, reason: e.target.value })}
          />
        </FormField>
      </form>
    </Dialog>
  )
}

export function VoidPunchDialog({ punch, onClose }: { punch: Punch; onClose: () => void }) {
  const invalidate = useInvalidatePunches()
  const [reason, setReason] = useState('')
  const { errors, error, reset, handle } = useFormErrors()
  const voidPunch = useTimeclockPunchesVoidCreate({
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
      title="Anular marcación"
      description={`${punch.employee_name} · ${formatDay(punch.timestamp)} ${formatTime(punch.timestamp)}. No se borra: queda anulada con el motivo y visible en el historial.`}
      footer={
        <>
          <Button variant="outline" onClick={onClose}>
            Cancelar
          </Button>
          <Button type="submit" form="void-form" variant="danger" loading={voidPunch.isPending}>
            Anular
          </Button>
        </>
      }
    >
      <form
        id="void-form"
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault()
          reset()
          voidPunch.mutate({ id: punch.id, data: { reason } })
        }}
      >
        {error && <Alert>{error}</Alert>}
        <FormField id="void-reason" label="Motivo" error={errors.reason}>
          <Input
            id="void-reason"
            required
            placeholder="Marcación doble, empleado equivocado…"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
          />
        </FormField>
      </form>
    </Dialog>
  )
}
