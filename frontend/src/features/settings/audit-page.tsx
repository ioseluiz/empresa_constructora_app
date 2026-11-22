import { ChevronDown, ChevronLeft, ChevronRight, History } from 'lucide-react'
import { Fragment, useState } from 'react'
import { useAuditLogsList } from '@/api/generated/audit/audit'
import type { AuditLog, AuditLogsListAction } from '@/api/generated/model'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { EmptyState, LoadingBlock, PageHeader } from '@/components/ui/page'
import { formatDateTime } from '@/lib/format'
import { Select } from '@/components/ui/select'
import { Table, TBody, TD, TH, THead, TR } from '@/components/ui/table'

const ACTIONS: Record<string, string> = {
  create: 'Creación',
  update: 'Modificación',
  delete: 'Eliminación',
  invite: 'Invitación',
  accept: 'Aceptación',
  revoke: 'Revocación',
  approve: 'Aprobación',
  export: 'Exportación',
}

const OBJECT_TYPES: Record<string, string> = {
  'tenants.tenant': 'Empresa',
  'tenants.membership': 'Usuario',
  'iam.role': 'Rol',
  'iam.invitation': 'Invitación',
}

function formatValue(value: unknown) {
  if (value === null || value === undefined || value === '') return '—'
  if (Array.isArray(value)) return value.join(', ') || '—'
  if (typeof value === 'boolean') return value ? 'Sí' : 'No'
  return typeof value === 'object' ? JSON.stringify(value) : String(value)
}

function Changes({ log }: { log: AuditLog }) {
  const entries = Object.entries(log.changes ?? {}) as [string, unknown][]
  if (entries.length === 0) return <p className="text-muted-foreground">Sin detalle de cambios.</p>
  const isDiff = entries.every(([, v]) => v && typeof v === 'object' && 'antes' in (v as object))
  return (
    <dl className="grid gap-x-6 gap-y-1 text-xs sm:grid-cols-[max-content_1fr]">
      {entries.map(([field, value]) => (
        <Fragment key={field}>
          <dt className="font-medium">{field}</dt>
          <dd className="text-muted-foreground">
            {isDiff ? (
              <>
                <span className="line-through">
                  {formatValue((value as { antes: unknown }).antes)}
                </span>
                {' → '}
                <span className="text-foreground">
                  {formatValue((value as { despues: unknown }).despues)}
                </span>
              </>
            ) : (
              formatValue(value)
            )}
          </dd>
        </Fragment>
      ))}
    </dl>
  )
}

export function AuditPage() {
  const [page, setPage] = useState(1)
  const [action, setAction] = useState('')
  const [search, setSearch] = useState('')
  const [expanded, setExpanded] = useState<string | null>(null)
  const logs = useAuditLogsList({
    page,
    search: search || undefined,
    action: (action || undefined) as AuditLogsListAction | undefined,
  })
  const rows = logs.data?.results ?? []

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <PageHeader
        title="Auditoría"
        description="Registro inalterable de quién cambió qué y cuándo."
      />
      <div className="flex flex-wrap gap-3">
        <Input
          type="search"
          placeholder="Buscar por usuario u objeto…"
          value={search}
          onChange={(e) => {
            setSearch(e.target.value)
            setPage(1)
          }}
          className="max-w-xs"
          aria-label="Buscar en la bitácora"
        />
        <Select
          value={action}
          onChange={(e) => {
            setAction(e.target.value)
            setPage(1)
          }}
          aria-label="Filtrar por acción"
        >
          <option value="">Todas las acciones</option>
          {Object.entries(ACTIONS).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </Select>
      </div>
      {logs.isPending ? (
        <LoadingBlock />
      ) : rows.length === 0 ? (
        <EmptyState icon={History} title="Sin registros" />
      ) : (
        <Table>
          <THead>
            <tr>
              <TH className="w-8" />
              <TH>Fecha</TH>
              <TH>Usuario</TH>
              <TH>Acción</TH>
              <TH>Objeto</TH>
              <TH>IP</TH>
            </tr>
          </THead>
          <TBody>
            {rows.map((log) => (
              <Fragment key={log.id}>
                <TR
                  className="cursor-pointer"
                  onClick={() => setExpanded(expanded === log.id ? null : log.id)}
                >
                  <TD>
                    <ChevronDown
                      className={`text-muted-foreground size-4 transition-transform ${expanded === log.id ? '' : '-rotate-90'}`}
                    />
                  </TD>
                  <TD className="whitespace-nowrap">{formatDateTime(log.created_at)}</TD>
                  <TD>{log.actor_email || 'Sistema'}</TD>
                  <TD>
                    <Badge>{log.action_display}</Badge>
                  </TD>
                  <TD>
                    <span className="text-muted-foreground">
                      {OBJECT_TYPES[log.object_type] ?? log.object_type}:
                    </span>{' '}
                    {log.object_repr}
                  </TD>
                  <TD className="text-muted-foreground">{log.ip_address ?? '—'}</TD>
                </TR>
                {expanded === log.id && (
                  <tr className="bg-muted/30">
                    <td />
                    <td colSpan={5} className="px-4 py-3">
                      <Changes log={log} />
                    </td>
                  </tr>
                )}
              </Fragment>
            ))}
          </TBody>
        </Table>
      )}
      {(logs.data?.previous || logs.data?.next) && (
        <div className="flex items-center justify-end gap-2 text-sm">
          <Button
            variant="outline"
            size="sm"
            disabled={!logs.data?.previous}
            onClick={() => setPage(page - 1)}
          >
            <ChevronLeft className="size-4" /> Anterior
          </Button>
          <span className="text-muted-foreground">Página {page}</span>
          <Button
            variant="outline"
            size="sm"
            disabled={!logs.data?.next}
            onClick={() => setPage(page + 1)}
          >
            Siguiente <ChevronRight className="size-4" />
          </Button>
        </div>
      )}
    </div>
  )
}
