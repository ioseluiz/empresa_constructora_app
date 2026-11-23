import { useQueryClient } from '@tanstack/react-query'
import { CalendarRange, Plus, Trash2, Users } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import type { Shift } from '@/api/generated/model'
import {
  getTimeclockShiftAssignmentsListQueryKey,
  getTimeclockShiftsListQueryKey,
  useTimeclockShiftAssignmentsBulkCreate,
  useTimeclockShiftAssignmentsDestroy,
  useTimeclockShiftAssignmentsList,
  useTimeclockShiftsCreate,
  useTimeclockShiftsList,
  useTimeclockShiftsPartialUpdate,
} from '@/api/generated/marcaciones/marcaciones'
import { useHrEmployeesList } from '@/api/generated/personal/personal'
import { useProjectsList } from '@/api/generated/proyectos/proyectos'
import { Alert } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox, Switch } from '@/components/ui/checkbox'
import { Dialog } from '@/components/ui/dialog'
import { FormField } from '@/components/ui/form-field'
import { Input } from '@/components/ui/input'
import { EmptyState, LoadingBlock, PageHeader } from '@/components/ui/page'
import { Pager } from '@/components/ui/pager'
import { Select } from '@/components/ui/select'
import { Table, TBody, TD, TH, THead, TR } from '@/components/ui/table'
import { useAccess } from '@/features/access/use-access'
import { todayISO } from '@/features/employees/constants'
import { formatDate, formatMinutes } from '@/lib/format'
import { useFormErrors } from '@/lib/use-form-errors'
import { cn } from '@/lib/utils'
import { WEEKDAYS } from './constants'
import { TimeclockTabs } from './timeclock-tabs'

const hhmm = (t: string) => t.slice(0, 5)

function ShiftDialog({ shift, onClose }: { shift?: Shift; onClose: () => void }) {
  const queryClient = useQueryClient()
  const [form, setForm] = useState({
    code: shift?.code ?? '',
    name: shift?.name ?? '',
    start_time: shift ? hhmm(shift.start_time) : '07:00',
    end_time: shift ? hhmm(shift.end_time) : '16:00',
    break_minutes: String(shift?.break_minutes ?? 60),
    break_after_minutes: String(shift?.break_after_minutes ?? 360),
    late_tolerance_minutes: String(shift?.late_tolerance_minutes ?? 5),
    overtime_rounding_minutes: String(shift?.overtime_rounding_minutes ?? 15),
  })
  const [workdays, setWorkdays] = useState<number[]>(shift?.workdays ?? [0, 1, 2, 3, 4])
  const [flags, setFlags] = useState({
    count_early_arrival: shift?.count_early_arrival ?? false,
    is_default: shift?.is_default ?? false,
    is_active: shift?.is_active ?? true,
  })
  const { errors, error, reset, handle } = useFormErrors()
  const onSuccess = () => {
    void queryClient.invalidateQueries({ queryKey: getTimeclockShiftsListQueryKey() })
    onClose()
  }
  const create = useTimeclockShiftsCreate({ mutation: { onSuccess, onError: handle } })
  const update = useTimeclockShiftsPartialUpdate({ mutation: { onSuccess, onError: handle } })
  const submit = (e: FormEvent) => {
    e.preventDefault()
    reset()
    const data = {
      ...form,
      ...flags,
      workdays,
      break_minutes: Number(form.break_minutes),
      break_after_minutes: Number(form.break_after_minutes),
      late_tolerance_minutes: Number(form.late_tolerance_minutes),
      overtime_rounding_minutes: Number(form.overtime_rounding_minutes),
    }
    if (shift) update.mutate({ id: shift.id, data })
    else create.mutate({ data })
  }
  const set = (key: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm({ ...form, [key]: e.target.value })
  const crosses = form.end_time <= form.start_time
  const number = (key: keyof typeof form, label: string, hint?: string) => (
    <FormField
      id={`shift-${key}`}
      label={label}
      error={errors[key]}
      hint={hint && <span className="text-muted-foreground text-xs">{hint}</span>}
    >
      <Input
        id={`shift-${key}`}
        type="number"
        min="0"
        required
        value={form[key]}
        onChange={set(key)}
      />
    </FormField>
  )

  return (
    <Dialog
      open
      size="lg"
      onOpenChange={(o) => !o && onClose()}
      title={shift ? `Editar ${shift.name}` : 'Nuevo horario'}
      description="Define la hora de entrada y salida, el almuerzo y los días laborables. Los demás días son de descanso."
      footer={
        <>
          <Button variant="outline" onClick={onClose}>
            Cancelar
          </Button>
          <Button type="submit" form="shift-form" loading={create.isPending || update.isPending}>
            Guardar
          </Button>
        </>
      }
    >
      <form id="shift-form" onSubmit={submit} className="space-y-5">
        {error && <Alert>{error}</Alert>}
        <div className="grid gap-4 sm:grid-cols-[8rem_1fr]">
          <FormField id="shift-code" label="Código" error={errors.code}>
            <Input id="shift-code" required value={form.code} onChange={set('code')} />
          </FormField>
          <FormField id="shift-name" label="Nombre" error={errors.name}>
            <Input
              id="shift-name"
              required
              placeholder="Diurno obra"
              value={form.name}
              onChange={set('name')}
            />
          </FormField>
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <FormField id="shift-start" label="Entrada" error={errors.start_time}>
            <Input
              id="shift-start"
              type="time"
              required
              value={form.start_time}
              onChange={set('start_time')}
            />
          </FormField>
          <FormField
            id="shift-end"
            label="Salida"
            error={errors.end_time}
            hint={crosses && <span className="text-muted-foreground text-xs">Día siguiente</span>}
          >
            <Input
              id="shift-end"
              type="time"
              required
              value={form.end_time}
              onChange={set('end_time')}
            />
          </FormField>
          {number('break_minutes', 'Almuerzo (min)', 'Sin pago')}
          {number('break_after_minutes', 'Descontarlo si la jornada supera (min)')}
          {number('late_tolerance_minutes', 'Tolerancia de llegada (min)')}
          {number('overtime_rounding_minutes', 'Redondeo de extras (min)', '0 = exacto')}
        </div>
        <div className="space-y-2">
          <p className="text-sm font-medium">Días laborables</p>
          <div className="flex flex-wrap gap-2">
            {WEEKDAYS.map(([d, label]) => {
              const on = workdays.includes(d)
              return (
                <button
                  key={d}
                  type="button"
                  aria-pressed={on}
                  onClick={() =>
                    setWorkdays(on ? workdays.filter((x) => x !== d) : [...workdays, d].sort())
                  }
                  className={cn(
                    'h-9 w-12 rounded-md border text-sm transition-colors',
                    on ? 'border-primary bg-primary text-primary-foreground' : 'hover:bg-muted',
                  )}
                >
                  {label}
                </button>
              )
            })}
          </div>
          {errors.workdays && <p className="text-danger text-xs">{errors.workdays}</p>}
        </div>
        <div className="space-y-2">
          <label className="flex items-center gap-2 text-sm">
            <Checkbox
              checked={flags.count_early_arrival}
              onChange={(e) => setFlags({ ...flags, count_early_arrival: e.target.checked })}
            />
            Pagar el tiempo antes de la hora de entrada
          </label>
          <label className="flex items-center gap-2 text-sm">
            <Checkbox
              checked={flags.is_default}
              onChange={(e) => setFlags({ ...flags, is_default: e.target.checked })}
            />
            Horario por defecto (empleados sin horario asignado)
          </label>
          <label className="flex items-center gap-2 text-sm">
            <Switch
              checked={flags.is_active}
              onCheckedChange={(v) => setFlags({ ...flags, is_active: v })}
            />{' '}
            Activo
          </label>
        </div>
      </form>
    </Dialog>
  )
}

function AssignDialog({ shifts, onClose }: { shifts: Shift[]; onClose: () => void }) {
  const queryClient = useQueryClient()
  const projects = useProjectsList({ ordering: 'code', status: 'active' })
  const [shift, setShift] = useState('')
  const [startDate, setStartDate] = useState(todayISO())
  const [project, setProject] = useState('')
  const [search, setSearch] = useState('')
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [result, setResult] = useState<{ assigned: number; skipped: string[] } | null>(null)
  const employees = useHrEmployeesList({
    status: 'active',
    project: project || undefined,
    search: search || undefined,
    ordering: 'last_name',
  })
  const rows = employees.data?.results ?? []
  const allSelected = rows.length > 0 && rows.every((e) => selected.has(e.id))
  const { errors, error, reset, handle } = useFormErrors()
  const bulk = useTimeclockShiftAssignmentsBulkCreate({
    mutation: {
      onSuccess: (r) => {
        void queryClient.invalidateQueries({ queryKey: getTimeclockShiftAssignmentsListQueryKey() })
        setResult(r)
      },
      onError: handle,
    },
  })
  if (result)
    return (
      <Dialog
        open
        onOpenChange={(o) => !o && onClose()}
        title="Horario asignado"
        footer={<Button onClick={onClose}>Listo</Button>}
      >
        <div className="space-y-3 text-sm">
          <p>
            Se asignó el horario a <strong>{result.assigned}</strong> empleados. Recalcula las
            jornadas del período para aplicar el cambio.
          </p>
          {result.skipped.length > 0 && <Alert>Omitidos: {result.skipped.join('; ')}.</Alert>}
        </div>
      </Dialog>
    )
  return (
    <Dialog
      open
      size="lg"
      onOpenChange={(o) => !o && onClose()}
      title="Asignar horario"
      description="Desde la fecha indicada; el horario anterior de cada empleado se cierra el día previo."
      footer={
        <>
          <Button variant="outline" onClick={onClose}>
            Cancelar
          </Button>
          <Button
            type="submit"
            form="assign-form"
            disabled={selected.size === 0}
            loading={bulk.isPending}
          >
            Asignar {selected.size > 0 ? `(${selected.size})` : ''}
          </Button>
        </>
      }
    >
      <form
        id="assign-form"
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault()
          reset()
          bulk.mutate({ data: { shift, start_date: startDate, employees: [...selected] } })
        }}
      >
        {error && <Alert>{error}</Alert>}
        <div className="grid gap-4 sm:grid-cols-3">
          <FormField id="asg-shift" label="Horario" error={errors.shift}>
            <Select
              id="asg-shift"
              className="w-full"
              required
              value={shift}
              onChange={(e) => setShift(e.target.value)}
            >
              <option value="">Selecciona…</option>
              {shifts
                .filter((s) => s.is_active)
                .map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name}
                  </option>
                ))}
            </Select>
          </FormField>
          <FormField id="asg-date" label="Desde" error={errors.start_date}>
            <Input
              id="asg-date"
              type="date"
              required
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
            />
          </FormField>
          <FormField id="asg-project" label="Empleados del proyecto">
            <Select
              id="asg-project"
              className="w-full"
              value={project}
              onChange={(e) => {
                setProject(e.target.value)
                setSelected(new Set())
              }}
            >
              <option value="">Todos</option>
              {projects.data?.results.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.code} · {p.name}
                </option>
              ))}
            </Select>
          </FormField>
        </div>
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
          <div className="rounded-md border">
            {employees.isPending ? (
              <LoadingBlock />
            ) : rows.length === 0 ? (
              <p className="text-muted-foreground p-4 text-sm">No hay empleados activos.</p>
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
                    <Checkbox
                      checked={selected.has(e.id)}
                      onChange={() => {
                        const next = new Set(selected)
                        if (next.has(e.id)) next.delete(e.id)
                        else next.add(e.id)
                        setSelected(next)
                      }}
                    />
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

export function ShiftsPage() {
  const queryClient = useQueryClient()
  const { can } = useAccess()
  const canEdit = can('timeclock.import')
  const shifts = useTimeclockShiftsList()
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const assignments = useTimeclockShiftAssignmentsList({ search: search || undefined, page })
  const [modal, setModal] = useState<{ kind: 'shift'; shift?: Shift } | { kind: 'assign' } | null>(
    null,
  )
  const destroy = useTimeclockShiftAssignmentsDestroy({
    mutation: {
      onSuccess: () =>
        void queryClient.invalidateQueries({
          queryKey: getTimeclockShiftAssignmentsListQueryKey(),
        }),
    },
  })
  const today = todayISO()

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <PageHeader
        title="Marcaciones"
        description="Horarios de trabajo: definen la entrada, el almuerzo, la tardanza y los días de descanso."
        actions={
          canEdit && (
            <>
              <Button variant="outline" onClick={() => setModal({ kind: 'assign' })}>
                <Users className="size-4" /> Asignar horario
              </Button>
              <Button onClick={() => setModal({ kind: 'shift' })}>
                <Plus className="size-4" /> Nuevo horario
              </Button>
            </>
          )
        }
      />
      <TimeclockTabs />
      {shifts.isPending ? (
        <LoadingBlock />
      ) : (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {shifts.data?.map((s) => (
            <button
              key={s.id}
              type="button"
              disabled={!canEdit}
              onClick={() => setModal({ kind: 'shift', shift: s })}
              className={cn(
                'bg-card space-y-3 rounded-lg border p-4 text-left shadow-xs transition-colors',
                canEdit && 'hover:border-primary/60',
                !s.is_active && 'opacity-60',
              )}
            >
              <div className="flex items-start justify-between gap-2">
                <div>
                  <p className="font-medium">{s.name}</p>
                  <p className="text-muted-foreground font-mono text-xs">{s.code}</p>
                </div>
                <div className="flex gap-1">
                  {s.is_default && <Badge variant="success">Por defecto</Badge>}
                  {!s.is_active && <Badge>Inactivo</Badge>}
                </div>
              </div>
              <p className="text-2xl font-semibold tabular-nums">
                {hhmm(s.start_time)} – {hhmm(s.end_time)}
                {s.crosses_midnight && (
                  <span className="text-muted-foreground ml-1 text-xs font-normal">(+1 día)</span>
                )}
              </p>
              <div className="flex gap-1">
                {WEEKDAYS.map(([d, label]) => (
                  <span
                    key={d}
                    className={cn(
                      'rounded px-1.5 py-0.5 text-[11px]',
                      s.workdays?.includes(d)
                        ? 'bg-primary/10 text-primary font-medium'
                        : 'text-muted-foreground',
                    )}
                  >
                    {label}
                  </span>
                ))}
              </div>
              <p className="text-muted-foreground text-xs">
                {formatMinutes(s.paid_minutes)} h pagadas · almuerzo {s.break_minutes} min ·
                tolerancia {s.late_tolerance_minutes} min
              </p>
            </button>
          ))}
        </div>
      )}

      <section className="space-y-3">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold">Horario de cada empleado</h2>
            <p className="text-muted-foreground text-sm">
              Quien no tenga horario asignado usa el horario por defecto.
            </p>
          </div>
          <Input
            type="search"
            placeholder="Buscar empleado…"
            aria-label="Buscar empleado"
            className="max-w-56"
            value={search}
            onChange={(e) => {
              setSearch(e.target.value)
              setPage(1)
            }}
          />
        </div>
        {assignments.isPending ? (
          <LoadingBlock />
        ) : (assignments.data?.results.length ?? 0) === 0 ? (
          <EmptyState
            icon={CalendarRange}
            title="Sin asignaciones"
            description="Todos usan el horario por defecto."
          />
        ) : (
          <>
            <Table>
              <THead>
                <tr>
                  <TH>Empleado</TH>
                  <TH>Horario</TH>
                  <TH>Desde</TH>
                  <TH>Hasta</TH>
                  {canEdit && <TH className="w-12" />}
                </tr>
              </THead>
              <TBody>
                {assignments.data?.results.map((a) => {
                  const current = a.start_date <= today && (!a.end_date || a.end_date >= today)
                  return (
                    <TR key={a.id}>
                      <TD>
                        {a.employee_name}{' '}
                        <span className="text-muted-foreground font-mono text-xs">
                          {a.employee_code}
                        </span>
                      </TD>
                      <TD>
                        {a.shift_name}
                        {current && (
                          <Badge className="ml-2" variant="success">
                            Actual
                          </Badge>
                        )}
                      </TD>
                      <TD className="whitespace-nowrap">{formatDate(a.start_date)}</TD>
                      <TD className="whitespace-nowrap">
                        {a.end_date ? formatDate(a.end_date) : '—'}
                      </TD>
                      {canEdit && (
                        <TD>
                          <Button
                            size="icon"
                            variant="ghost"
                            aria-label="Quitar asignación"
                            loading={destroy.isPending && destroy.variables?.id === a.id}
                            onClick={() => destroy.mutate({ id: a.id })}
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
            <Pager
              total={assignments.data?.count ?? 0}
              page={page}
              onPage={setPage}
              noun={['asignación', 'asignaciones']}
            />
          </>
        )}
      </section>

      {modal?.kind === 'shift' && (
        <ShiftDialog shift={modal.shift} onClose={() => setModal(null)} />
      )}
      {modal?.kind === 'assign' && (
        <AssignDialog shifts={shifts.data ?? []} onClose={() => setModal(null)} />
      )}
    </div>
  )
}
