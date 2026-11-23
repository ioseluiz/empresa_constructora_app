import { Clock, Pencil, Plus, XCircle } from 'lucide-react'
import { useState } from 'react'
import type {
  Punch,
  TimeclockPunchesListDirection,
  TimeclockPunchesListSource,
} from '@/api/generated/model'
import { useTimeclockPunchesList } from '@/api/generated/marcaciones/marcaciones'
import { useProjectsList } from '@/api/generated/proyectos/proyectos'
import { Badge } from '@/components/ui/badge'
import { Pager } from '@/components/ui/pager'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { EmptyState, LoadingBlock, PageHeader } from '@/components/ui/page'
import { Select } from '@/components/ui/select'
import { Table, TBody, TD, TH, THead, TR } from '@/components/ui/table'
import { useAccess } from '@/features/access/use-access'
import { todayISO } from '@/features/employees/constants'
import { Options } from '@/features/employees/employee-dialog'
import { formatDay, formatTime } from '@/lib/format'
import { cn } from '@/lib/utils'
import { daysAgoISO, DIRECTIONS, SOURCES } from './constants'
import { CorrectPunchDialog, ManualPunchDialog, VoidPunchDialog } from './punch-dialogs'
import { TimeclockTabs } from './timeclock-tabs'

type Modal = { kind: 'manual' } | { kind: 'correct' | 'void'; punch: Punch } | null

function DirectionBadge({ punch }: { punch: Punch }) {
  const variant = punch.direction === 'in' ? 'success' : 'neutral'
  return (
    <Badge variant={punch.direction === 'unknown' ? 'danger' : variant}>
      {punch.direction_display}
    </Badge>
  )
}

export function PunchesPage() {
  const { can } = useAccess()
  const canManual = can('timeclock.manual')
  const [filters, setFilters] = useState({
    date_from: daysAgoISO(6),
    date_to: todayISO(),
    project: '',
    source: '',
    direction: '',
    search: '',
    include_void: false,
  })
  const [page, setPage] = useState(1)
  const [modal, setModal] = useState<Modal>(null)
  const projects = useProjectsList({ ordering: 'code' })
  const punches = useTimeclockPunchesList({
    date_from: filters.date_from || undefined,
    date_to: filters.date_to || undefined,
    project: filters.project || undefined,
    source: (filters.source || undefined) as TimeclockPunchesListSource | undefined,
    direction: (filters.direction || undefined) as TimeclockPunchesListDirection | undefined,
    search: filters.search || undefined,
    include_void: filters.include_void || undefined,
    page,
  })
  const rows = punches.data?.results ?? []
  const total = punches.data?.count ?? 0
  const set = (key: keyof typeof filters, value: string | boolean) => {
    setFilters({ ...filters, [key]: value })
    setPage(1)
  }

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <PageHeader
        title="Marcaciones"
        description="Entradas y salidas importadas de los relojes, de Excel/CSV o registradas a mano."
        actions={
          canManual && (
            <Button onClick={() => setModal({ kind: 'manual' })}>
              <Plus className="size-4" /> Registro manual
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
          {projects.data?.results.map((p) => (
            <option key={p.id} value={p.id}>
              {p.code} · {p.name}
            </option>
          ))}
        </Select>
        <Select
          aria-label="Origen"
          value={filters.source}
          onChange={(e) => set('source', e.target.value)}
        >
          <Options empty="Todo origen" items={SOURCES} />
        </Select>
        <Select
          aria-label="Tipo"
          value={filters.direction}
          onChange={(e) => set('direction', e.target.value)}
        >
          <Options empty="Entradas y salidas" items={DIRECTIONS} />
        </Select>
        <Input
          type="search"
          placeholder="Empleado, cédula o número…"
          aria-label="Buscar empleado"
          className="max-w-56"
          value={filters.search}
          onChange={(e) => set('search', e.target.value)}
        />
        <label className="flex items-center gap-2 pb-2 text-sm">
          <Checkbox
            checked={filters.include_void}
            onChange={(e) => set('include_void', e.target.checked)}
          />
          Ver anuladas
        </label>
      </div>
      {punches.isPending ? (
        <LoadingBlock />
      ) : rows.length === 0 ? (
        <EmptyState
          icon={Clock}
          title="Sin marcaciones en el período"
          description="Importa el archivo del reloj o registra las marcaciones manualmente."
        />
      ) : (
        <>
          <Table>
            <THead>
              <tr>
                <TH>Empleado</TH>
                <TH>Fecha</TH>
                <TH>Hora</TH>
                <TH>Tipo</TH>
                <TH>Origen</TH>
                <TH>Proyecto</TH>
                {canManual && <TH className="w-24" />}
              </tr>
            </THead>
            <TBody>
              {rows.map((p) => (
                <TR key={p.id} className={cn(p.is_void && 'opacity-60')}>
                  <TD>
                    <p className={cn('font-medium', p.is_void && 'line-through')}>
                      {p.employee_name}
                    </p>
                    <p className="text-muted-foreground font-mono text-xs">{p.employee_code}</p>
                  </TD>
                  <TD className="whitespace-nowrap capitalize">{formatDay(p.timestamp)}</TD>
                  <TD className="font-mono tabular-nums">{formatTime(p.timestamp)}</TD>
                  <TD>
                    <DirectionBadge punch={p} />
                  </TD>
                  <TD>
                    <p>{p.source_display}</p>
                    <p className="text-muted-foreground text-xs">
                      {p.is_void
                        ? `Anulada: ${p.void_reason}`
                        : p.corrects
                          ? `Corrección: ${p.reason}`
                          : p.device_name || p.reason}
                    </p>
                  </TD>
                  <TD className="text-muted-foreground">{p.project_code ?? 'Oficina central'}</TD>
                  {canManual && (
                    <TD className="text-right whitespace-nowrap">
                      {!p.is_void && (
                        <>
                          <Button
                            size="icon"
                            variant="ghost"
                            aria-label="Corregir"
                            title="Corregir"
                            onClick={() => setModal({ kind: 'correct', punch: p })}
                          >
                            <Pencil className="size-4" />
                          </Button>
                          <Button
                            size="icon"
                            variant="ghost"
                            aria-label="Anular"
                            title="Anular"
                            onClick={() => setModal({ kind: 'void', punch: p })}
                          >
                            <XCircle className="size-4" />
                          </Button>
                        </>
                      )}
                    </TD>
                  )}
                </TR>
              ))}
            </TBody>
          </Table>
          <Pager total={total} page={page} onPage={setPage} noun={['marcación', 'marcaciones']} />
        </>
      )}
      {modal?.kind === 'manual' && <ManualPunchDialog onClose={() => setModal(null)} />}
      {modal?.kind === 'correct' && (
        <CorrectPunchDialog punch={modal.punch} onClose={() => setModal(null)} />
      )}
      {modal?.kind === 'void' && (
        <VoidPunchDialog punch={modal.punch} onClose={() => setModal(null)} />
      )}
    </div>
  )
}
