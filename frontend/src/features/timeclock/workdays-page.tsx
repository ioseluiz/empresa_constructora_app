import { useQueryClient } from '@tanstack/react-query'
import { CalendarClock, CheckCircle2, RefreshCw, RotateCcw } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import type {
  TimeclockWorkdaysListParams,
  TimeclockWorkdaysListStatus,
  WorkDay,
} from '@/api/generated/model'
import {
  getTimeclockWorkdaysListQueryKey,
  getTimeclockWorkdaysSummaryRetrieveQueryKey,
  useTimeclockWorkdaysApproveCreate,
  useTimeclockWorkdaysCalculateCreate,
  useTimeclockWorkdaysList,
  useTimeclockWorkdaysReopenCreate,
  useTimeclockWorkdaysSummaryRetrieve,
} from '@/api/generated/marcaciones/marcaciones'
import { useProjectsList } from '@/api/generated/proyectos/proyectos'
import { Alert } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import { Dialog } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { EmptyState, LoadingBlock, PageHeader } from '@/components/ui/page'
import { Pager } from '@/components/ui/pager'
import { Select } from '@/components/ui/select'
import { Table, TBody, TD, TH, THead, TR } from '@/components/ui/table'
import { useAccess } from '@/features/access/use-access'
import { todayISO } from '@/features/employees/constants'
import { formatDay, formatHour, formatMinutes } from '@/lib/format'
import { useFormErrors } from '@/lib/use-form-errors'
import { cn } from '@/lib/utils'
import { mondayISO, WORKDAY_STATUS } from './constants'
import { TimeclockTabs } from './timeclock-tabs'

const ISSUE_FILTERS: [string, string][] = [
  ['missing_out', 'Falta la salida'],
  ['missing_in', 'Falta la entrada'],
  ['absent', 'Ausencias'],
  ['late', 'Tardanzas'],
  ['overtime_limit', 'Más de 3 h extra'],
  ['unassigned_project', 'Proyecto no asignado'],
]

function OvertimeCell({ w }: { w: WorkDay }) {
  if (!w.overtime_minutes) return <span className="text-muted-foreground">—</span>
  const parts = [
    ['D', w.overtime_day_minutes, 'Extra diurna (+25 %)'],
    ['N', w.overtime_night_minutes, 'Extra nocturna (+50 %)'],
    ['M', w.overtime_mixed_minutes, 'Prolongación nocturna (+75 %)'],
  ] as const
  return (
    <div className="flex flex-col items-end">
      <span className="font-medium tabular-nums">{formatMinutes(w.overtime_minutes)}</span>
      <span className="text-muted-foreground text-[11px]">
        {parts
          .filter(([, m]) => m > 0)
          .map(([k, m, title]) => (
            <abbr key={k} title={title} className="ml-1 no-underline">
              {k} {formatMinutes(m)}
            </abbr>
          ))}
      </span>
    </div>
  )
}

function WorkDayDialog({
  w,
  canApprove,
  onClose,
  onChanged,
}: {
  w: WorkDay
  canApprove: boolean
  onClose: () => void
  onChanged: () => void
}) {
  const { error, reset, handle } = useFormErrors()
  const opts = {
    mutation: {
      onSuccess: () => {
        onChanged()
        onClose()
      },
      onError: handle,
    },
  }
  const approve = useTimeclockWorkdaysApproveCreate(opts)
  const reopen = useTimeclockWorkdaysReopenCreate(opts)
  const rows: [string, string][] = [
    ['Horario', w.shift_name ?? 'Sin horario'],
    ['Tipo de día', w.day_kind_display],
    ['Jornada', w.jornada_display || '—'],
    ['Trabajado', formatMinutes(w.worked_minutes)],
    ['Descanso descontado', formatMinutes(w.break_minutes)],
    ['Ordinarias', formatMinutes(w.ordinary_minutes)],
    ['Extra diurna (+25 %)', formatMinutes(w.overtime_day_minutes)],
    ['Extra nocturna (+50 %)', formatMinutes(w.overtime_night_minutes)],
    ['Prolongación nocturna (+75 %)', formatMinutes(w.overtime_mixed_minutes)],
    ['Tardanza', formatMinutes(w.late_minutes)],
    ['Faltante', formatMinutes(w.missing_minutes)],
  ]
  return (
    <Dialog
      open
      size="lg"
      onOpenChange={(o) => !o && onClose()}
      title={`${w.employee_name} · ${formatDay(`${w.date}T12:00:00`)}`}
      description={`${w.project_code ?? 'Oficina central'} · ${w.status_display}${w.approved_by_email ? ` por ${w.approved_by_email}` : ''}`}
      footer={
        <>
          <Link
            to="/marcaciones"
            className="text-primary mr-auto self-center text-sm hover:underline"
          >
            Corregir marcaciones
          </Link>
          {canApprove && w.status === 'approved' && (
            <Button
              variant="outline"
              loading={reopen.isPending}
              onClick={() => {
                reset()
                reopen.mutate({ id: w.id })
              }}
            >
              <RotateCcw className="size-4" /> Reabrir
            </Button>
          )}
          {canApprove && w.status !== 'approved' && (
            <Button
              disabled={w.blocking}
              loading={approve.isPending}
              onClick={() => {
                reset()
                approve.mutate({ data: { ids: [w.id] } })
              }}
            >
              <CheckCircle2 className="size-4" /> Aprobar
            </Button>
          )}
        </>
      }
    >
      <div className="space-y-4">
        {error && <Alert>{error}</Alert>}
        {w.issue_labels.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {w.issue_labels.map((label) => (
              <Badge key={label} variant="danger">
                {label}
              </Badge>
            ))}
          </div>
        )}
        {w.blocking && (
          <p className="text-muted-foreground text-sm">
            Faltan marcaciones: regístralas o corrígelas en Marcaciones y la jornada se recalcula
            sola.
          </p>
        )}
        <div>
          <p className="mb-2 text-sm font-medium">Tramos trabajados</p>
          {(w.segments as [string, string][]).length === 0 ? (
            <p className="text-muted-foreground text-sm">Sin tramos completos.</p>
          ) : (
            <div className="flex flex-wrap gap-2">
              {(w.segments as [string, string][]).map(([s, e]) => (
                <span key={s} className="bg-muted rounded-md px-2 py-1 font-mono text-xs">
                  {formatHour(s)} – {formatHour(e)}
                </span>
              ))}
            </div>
          )}
        </div>
        <dl className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm sm:grid-cols-3">
          {rows.map(([term, value]) => (
            <div key={term}>
              <dt className="text-muted-foreground text-xs">{term}</dt>
              <dd className="font-medium tabular-nums">{value}</dd>
            </div>
          ))}
        </dl>
      </div>
    </Dialog>
  )
}

export function WorkDaysPage() {
  const queryClient = useQueryClient()
  const { can } = useAccess()
  const canApprove = can('timeclock.approve')
  const canCalculate = ['timeclock.manual', 'timeclock.import', 'timeclock.approve'].some(can)
  const [filters, setFilters] = useState({
    date_from: mondayISO(),
    date_to: todayISO(),
    project: '',
    status: '',
    issue: '',
    search: '',
  })
  const [page, setPage] = useState(1)
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [detail, setDetail] = useState<WorkDay | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const { error, reset, handle } = useFormErrors()
  const projects = useProjectsList({ ordering: 'code' })

  const params: TimeclockWorkdaysListParams = {
    date_from: filters.date_from || undefined,
    date_to: filters.date_to || undefined,
    project: filters.project && filters.project !== 'office' ? filters.project : undefined,
    office: filters.project === 'office' || undefined,
    status: (filters.status || undefined) as TimeclockWorkdaysListStatus | undefined,
    issue: filters.issue || undefined,
    search: filters.search || undefined,
  }
  const list = useTimeclockWorkdaysList({ ...params, page })
  const summary = useTimeclockWorkdaysSummaryRetrieve(params)
  const rows = list.data?.results ?? []
  const set = (key: keyof typeof filters, value: string) => {
    setFilters({ ...filters, [key]: value })
    setPage(1)
    setSelected(new Set())
  }
  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: getTimeclockWorkdaysListQueryKey() })
    void queryClient.invalidateQueries({ queryKey: getTimeclockWorkdaysSummaryRetrieveQueryKey() })
  }
  const calculate = useTimeclockWorkdaysCalculateCreate({
    mutation: {
      onSuccess: (r) => {
        refresh()
        setNotice(
          `Se calcularon ${r.workdays} jornadas.${r.skipped_approved ? ` ${r.skipped_approved} aprobadas no se modificaron.` : ''}`,
        )
      },
      onError: handle,
    },
  })
  const approve = useTimeclockWorkdaysApproveCreate({
    mutation: {
      onSuccess: (r) => {
        refresh()
        setSelected(new Set())
        setNotice(`Se aprobaron ${r.approved} jornadas.`)
      },
      onError: handle,
    },
  })
  const approvable = rows.filter((w) => w.status !== 'approved' && !w.blocking)
  const allSelected = approvable.length > 0 && approvable.every((w) => selected.has(w.id))
  const toggle = (id: string) => {
    const next = new Set(selected)
    if (next.has(id)) next.delete(id)
    else next.add(id)
    setSelected(next)
  }

  const stats: [string, string | number, string?][] = summary.data
    ? [
        ['Jornadas', summary.data.total],
        [
          'Con inconsistencias',
          summary.data.review,
          summary.data.review ? 'text-danger' : undefined,
        ],
        ['Por aprobar', summary.data.pending],
        ['Horas ordinarias', formatMinutes(summary.data.ordinary_minutes)],
        ['Horas extra', formatMinutes(summary.data.overtime_minutes)],
      ]
    : []

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <PageHeader
        title="Marcaciones"
        description="Jornadas calculadas según el horario y la jornada legal. Al aprobarlas pasan a la planilla."
        actions={
          canCalculate && (
            <Button
              variant="outline"
              loading={calculate.isPending}
              onClick={() => {
                reset()
                setNotice(null)
                calculate.mutate({
                  data: {
                    date_from: filters.date_from,
                    date_to: filters.date_to,
                    project: params.project ?? null,
                  },
                })
              }}
            >
              <RefreshCw className="size-4" /> Calcular jornadas
            </Button>
          )
        }
      />
      <TimeclockTabs />
      <div className="flex flex-wrap items-end gap-3">
        <label className="space-y-1 text-xs">
          <span className="text-muted-foreground">Desde</span>
          <Input
            type="date"
            value={filters.date_from}
            onChange={(e) => set('date_from', e.target.value)}
          />
        </label>
        <label className="space-y-1 text-xs">
          <span className="text-muted-foreground">Hasta</span>
          <Input
            type="date"
            value={filters.date_to}
            onChange={(e) => set('date_to', e.target.value)}
          />
        </label>
        <Select
          aria-label="Proyecto"
          value={filters.project}
          onChange={(e) => set('project', e.target.value)}
        >
          <option value="">Todos los proyectos</option>
          <option value="office">Oficina central</option>
          {projects.data?.results.map((p) => (
            <option key={p.id} value={p.id}>
              {p.code} · {p.name}
            </option>
          ))}
        </Select>
        <Select
          aria-label="Estado"
          value={filters.status}
          onChange={(e) => set('status', e.target.value)}
        >
          <option value="">Todos los estados</option>
          {Object.entries(WORKDAY_STATUS).map(([v, { label }]) => (
            <option key={v} value={v}>
              {label}
            </option>
          ))}
        </Select>
        <Select
          aria-label="Inconsistencia"
          value={filters.issue}
          onChange={(e) => set('issue', e.target.value)}
        >
          <option value="">Toda inconsistencia</option>
          {ISSUE_FILTERS.map(([v, label]) => (
            <option key={v} value={v}>
              {label}
            </option>
          ))}
        </Select>
        <Input
          type="search"
          placeholder="Empleado…"
          aria-label="Buscar empleado"
          className="max-w-48"
          value={filters.search}
          onChange={(e) => set('search', e.target.value)}
        />
      </div>

      {error && <Alert>{error}</Alert>}
      {notice && <p className="text-success text-sm">{notice}</p>}

      {stats.length > 0 && (
        <div className="grid gap-4 sm:grid-cols-5">
          {stats.map(([label, value, color]) => (
            <Card key={label}>
              <CardHeader>
                <CardTitle>{label}</CardTitle>
              </CardHeader>
              <CardContent className={cn('text-2xl font-semibold tabular-nums', color)}>
                {value}
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {canApprove && rows.length > 0 && (
        // Siempre visible: así la tabla no se desplaza al seleccionar.
        <div
          className={cn(
            'flex items-center justify-between rounded-md border px-4 py-2 text-sm',
            selected.size > 0 ? 'bg-primary/5' : 'text-muted-foreground',
          )}
        >
          <span>
            {selected.size > 0
              ? `${selected.size} jornadas seleccionadas`
              : 'Selecciona las jornadas revisadas para aprobarlas.'}
          </span>
          <Button
            size="sm"
            disabled={selected.size === 0}
            loading={approve.isPending}
            onClick={() => {
              reset()
              setNotice(null)
              approve.mutate({ data: { ids: [...selected] } })
            }}
          >
            <CheckCircle2 className="size-4" /> Aprobar seleccionadas
          </Button>
        </div>
      )}

      {list.isPending ? (
        <LoadingBlock />
      ) : rows.length === 0 ? (
        <EmptyState
          icon={CalendarClock}
          title="Sin jornadas en el período"
          description={
            canCalculate
              ? 'Usa “Calcular jornadas” después de importar o registrar las marcaciones.'
              : undefined
          }
        />
      ) : (
        <>
          <Table>
            <THead>
              <tr>
                {canApprove && (
                  <TH className="w-10">
                    <Checkbox
                      aria-label="Seleccionar todas"
                      checked={allSelected}
                      onChange={() =>
                        setSelected(allSelected ? new Set() : new Set(approvable.map((w) => w.id)))
                      }
                    />
                  </TH>
                )}
                <TH>Empleado</TH>
                <TH>Fecha</TH>
                <TH>Entrada / salida</TH>
                <TH className="text-right">Ordinarias</TH>
                <TH className="text-right">Extras</TH>
                <TH>Observaciones</TH>
                <TH>Estado</TH>
              </tr>
            </THead>
            <TBody>
              {rows.map((w) => {
                const st = WORKDAY_STATUS[w.status]
                const selectable = w.status !== 'approved' && !w.blocking
                return (
                  <TR key={w.id} className="cursor-pointer" onClick={() => setDetail(w)}>
                    {canApprove && (
                      <TD onClick={(e) => e.stopPropagation()}>
                        <Checkbox
                          aria-label={`Seleccionar ${w.employee_name}`}
                          disabled={!selectable}
                          checked={selected.has(w.id)}
                          onChange={() => toggle(w.id)}
                        />
                      </TD>
                    )}
                    <TD>
                      <p className="font-medium">{w.employee_name}</p>
                      <p className="text-muted-foreground text-xs">
                        <span className="font-mono">{w.employee_code}</span> ·{' '}
                        {w.project_code ?? 'Oficina'}
                      </p>
                    </TD>
                    <TD className="whitespace-nowrap">
                      <span className="capitalize">{formatDay(`${w.date}T12:00:00`)}</span>
                      {w.day_kind !== 'regular' && (
                        <Badge
                          className="ml-2"
                          variant={w.day_kind === 'holiday' ? 'danger' : 'neutral'}
                        >
                          {w.day_kind_display}
                        </Badge>
                      )}
                    </TD>
                    <TD className="font-mono text-xs whitespace-nowrap tabular-nums">
                      {formatHour(w.first_in)} – {formatHour(w.last_out)}
                    </TD>
                    <TD className="text-right tabular-nums">{formatMinutes(w.ordinary_minutes)}</TD>
                    <TD className="text-right">
                      <OvertimeCell w={w} />
                    </TD>
                    <TD>
                      <div className="flex max-w-56 flex-wrap gap-1">
                        {w.issue_labels.map((label) => (
                          <Badge key={label} variant={w.blocking ? 'danger' : 'neutral'}>
                            {label}
                          </Badge>
                        ))}
                      </div>
                    </TD>
                    <TD>
                      <Badge variant={st.variant}>{st.label}</Badge>
                    </TD>
                  </TR>
                )
              })}
            </TBody>
          </Table>
          <Pager
            total={list.data?.count ?? 0}
            page={page}
            onPage={setPage}
            noun={['jornada', 'jornadas']}
          />
        </>
      )}
      {detail && (
        <WorkDayDialog
          w={detail}
          canApprove={canApprove}
          onClose={() => setDetail(null)}
          onChanged={refresh}
        />
      )}
    </div>
  )
}
