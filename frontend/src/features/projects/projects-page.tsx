import { HardHat, MapPin, Plus } from 'lucide-react'
import { useState } from 'react'
import type { Project, ProjectsListStatus } from '@/api/generated/model'
import { useProjectsList } from '@/api/generated/proyectos/proyectos'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { EmptyState, LoadingBlock, PageHeader } from '@/components/ui/page'
import { Select } from '@/components/ui/select'
import { Table, TBody, TD, TH, THead, TR } from '@/components/ui/table'
import { useAccess } from '@/features/access/use-access'
import { formatDate, formatMoney } from '@/lib/format'
import { PROJECT_STATUS } from './constants'
import { ProjectDialog } from './project-dialog'

export function ProjectsPage() {
  const { can } = useAccess()
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState('')
  const [editing, setEditing] = useState<Project | 'new' | null>(null)
  const projects = useProjectsList({
    search: search || undefined,
    status: (status || undefined) as ProjectsListStatus | undefined,
    ordering: 'code',
  })
  const rows = projects.data?.results ?? []
  const canManage = can('projects.manage')

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <PageHeader
        title="Proyectos"
        description="Obras de la empresa. La oficina central se gestiona en Centros de costo."
        actions={
          canManage && (
            <Button onClick={() => setEditing('new')}>
              <Plus className="size-4" /> Nuevo proyecto
            </Button>
          )
        }
      />
      <div className="flex flex-wrap gap-3">
        <Input
          type="search"
          placeholder="Buscar por código, nombre o cliente…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="max-w-sm"
          aria-label="Buscar proyectos"
        />
        <Select value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Estado">
          <option value="">Todos los estados</option>
          {Object.entries(PROJECT_STATUS).map(([v, { label }]) => (
            <option key={v} value={v}>
              {label}
            </option>
          ))}
        </Select>
      </div>
      {projects.isPending ? (
        <LoadingBlock />
      ) : rows.length === 0 ? (
        <EmptyState
          icon={HardHat}
          title={search || status ? 'Sin resultados' : 'Aún no hay proyectos'}
          description={
            canManage ? 'Crea el primer proyecto para empezar a asignar personal.' : undefined
          }
        />
      ) : (
        <Table>
          <THead>
            <tr>
              <TH>Proyecto</TH>
              <TH>Cliente</TH>
              <TH>Estado</TH>
              <TH>Inicio</TH>
              <TH>Fin estimado</TH>
              <TH className="text-right">Contrato</TH>
            </tr>
          </THead>
          <TBody>
            {rows.map((p) => {
              const st = PROJECT_STATUS[p.status ?? 'planning']
              return (
                <TR
                  key={p.id}
                  className={canManage ? 'cursor-pointer' : undefined}
                  onClick={() => canManage && setEditing(p)}
                >
                  <TD>
                    <p className="font-medium">
                      <span className="text-muted-foreground font-mono text-xs">{p.code}</span>{' '}
                      {p.name}
                    </p>
                    {p.province_display && (
                      <p className="text-muted-foreground flex items-center gap-1 text-xs">
                        <MapPin className="size-3" /> {p.province_display}
                      </p>
                    )}
                  </TD>
                  <TD className="text-muted-foreground">{p.client || '—'}</TD>
                  <TD>
                    <Badge variant={st.variant}>{st.label}</Badge>
                  </TD>
                  <TD className="whitespace-nowrap">{formatDate(p.start_date)}</TD>
                  <TD className="whitespace-nowrap">{formatDate(p.estimated_end_date)}</TD>
                  <TD className="text-right whitespace-nowrap tabular-nums">
                    {formatMoney(p.contract_amount)}
                  </TD>
                </TR>
              )
            })}
          </TBody>
        </Table>
      )}
      {editing && (
        <ProjectDialog
          key={editing === 'new' ? 'new' : editing.id}
          project={editing === 'new' ? undefined : editing}
          onClose={() => setEditing(null)}
        />
      )}
    </div>
  )
}
