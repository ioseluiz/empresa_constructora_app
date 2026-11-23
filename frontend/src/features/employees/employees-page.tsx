import { Plus, Users } from 'lucide-react'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import type { HrEmployeesListStatus } from '@/api/generated/model'
import { useHrEmployeesList } from '@/api/generated/personal/personal'
import { useProjectsList } from '@/api/generated/proyectos/proyectos'
import { Badge } from '@/components/ui/badge'
import { Pager } from '@/components/ui/pager'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { EmptyState, LoadingBlock, PageHeader } from '@/components/ui/page'
import { Select } from '@/components/ui/select'
import { Table, TBody, TD, TH, THead, TR } from '@/components/ui/table'
import { useAccess } from '@/features/access/use-access'
import { formatDate } from '@/lib/format'
import { EMPLOYEE_STATUS } from './constants'
import { EmployeeDialog } from './employee-dialog'

export function EmployeesPage() {
  const { can } = useAccess()
  const navigate = useNavigate()
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState('active')
  const [project, setProject] = useState('')
  const [page, setPage] = useState(1)
  const [creating, setCreating] = useState(false)
  const projects = useProjectsList({ ordering: 'code' })
  const employees = useHrEmployeesList({
    search: search || undefined,
    status: (status || undefined) as HrEmployeesListStatus | undefined,
    project: project || undefined,
    ordering: 'last_name',
    page,
  })
  const rows = employees.data?.results ?? []
  const total = employees.data?.count ?? 0
  const filtered = !!(search || project || status !== 'active')
  const filter =
    <T,>(setter: (v: T) => void) =>
    (v: T) => {
      setter(v)
      setPage(1)
    }

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <PageHeader
        title="Empleados"
        description="Expediente del personal de obra y oficina: contratos, salarios, proyectos y documentos."
        actions={
          can('hr.employee.manage') && (
            <Button onClick={() => setCreating(true)}>
              <Plus className="size-4" /> Nuevo empleado
            </Button>
          )
        }
      />
      <div className="flex flex-wrap gap-3">
        <Input
          type="search"
          placeholder="Buscar por nombre, cédula, nº de empleado o seguro social…"
          value={search}
          onChange={(e) => filter(setSearch)(e.target.value)}
          className="max-w-sm"
          aria-label="Buscar empleados"
        />
        <Select
          value={status}
          onChange={(e) => filter(setStatus)(e.target.value)}
          aria-label="Estado"
        >
          <option value="active">Activos</option>
          <option value="terminated">Retirados</option>
          <option value="">Todos</option>
        </Select>
        <Select
          value={project}
          onChange={(e) => filter(setProject)(e.target.value)}
          aria-label="Proyecto"
        >
          <option value="">Todos los proyectos</option>
          {projects.data?.results.map((p) => (
            <option key={p.id} value={p.id}>
              {p.code} · {p.name}
            </option>
          ))}
        </Select>
      </div>
      {employees.isPending ? (
        <LoadingBlock />
      ) : rows.length === 0 ? (
        <EmptyState
          icon={Users}
          title={filtered ? 'Sin resultados' : 'Aún no hay empleados'}
          description={
            !filtered && can('hr.employee.manage')
              ? 'Registra al primer empleado para crear su expediente.'
              : undefined
          }
        />
      ) : (
        <>
          <Table>
            <THead>
              <tr>
                <TH>Empleado</TH>
                <TH>Identificación</TH>
                <TH>Puesto</TH>
                <TH>Proyectos</TH>
                <TH>Ingreso</TH>
                <TH>Estado</TH>
              </tr>
            </THead>
            <TBody>
              {rows.map((e) => {
                const st = EMPLOYEE_STATUS[e.status]
                return (
                  <TR
                    key={e.id}
                    className="cursor-pointer"
                    onClick={() => void navigate(`/empleados/${e.id}`)}
                  >
                    <TD>
                      <p className="font-medium">{e.full_name}</p>
                      <p className="text-muted-foreground font-mono text-xs">{e.code}</p>
                    </TD>
                    <TD>
                      <p className="tabular-nums">{e.id_number}</p>
                      {e.css_number && (
                        <p className="text-muted-foreground text-xs">SS {e.css_number}</p>
                      )}
                    </TD>
                    <TD className="text-muted-foreground">{e.current_position ?? '—'}</TD>
                    <TD>
                      <div className="flex flex-wrap gap-1">
                        {e.current_projects.length === 0 ? (
                          <span className="text-muted-foreground">Oficina central</span>
                        ) : (
                          e.current_projects.map((p) => (
                            <Badge key={p.id} title={p.name}>
                              {p.code}
                            </Badge>
                          ))
                        )}
                      </div>
                    </TD>
                    <TD className="whitespace-nowrap">{formatDate(e.hire_date)}</TD>
                    <TD>
                      <Badge variant={st.variant}>{st.label}</Badge>
                    </TD>
                  </TR>
                )
              })}
            </TBody>
          </Table>
          <Pager total={total} page={page} onPage={setPage} noun={['empleado', 'empleados']} />
        </>
      )}
      {creating && (
        <EmployeeDialog
          onClose={() => setCreating(false)}
          onCreated={(e) => void navigate(`/empleados/${e.id}`)}
        />
      )}
    </div>
  )
}
