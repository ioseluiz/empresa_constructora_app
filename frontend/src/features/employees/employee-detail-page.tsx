import { ArrowLeft, Pencil } from 'lucide-react'
import { useState, type ReactNode } from 'react'
import { Link, useParams } from 'react-router-dom'
import type { Employee } from '@/api/generated/model'
import { useHrEmployeesRetrieve } from '@/api/generated/personal/personal'
import { Alert } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { LoadingBlock } from '@/components/ui/page'
import { useAccess } from '@/features/access/use-access'
import { PROVINCES } from '@/features/projects/constants'
import { formatDate } from '@/lib/format'
import { cn } from '@/lib/utils'
import { AssignmentsTab } from './assignments-tab'
import { EMPLOYEE_STATUS, MARITAL_STATUS } from './constants'
import { ContractsTab } from './contracts-tab'
import { DeductionsTab } from './deductions-tab'
import { DocumentsTab } from './documents-tab'
import { PayslipsTab } from './payslips-tab'
import { EmployeeDialog } from './employee-dialog'

const TABS = [
  { id: 'datos', label: 'Datos personales' },
  { id: 'contratos', label: 'Contratos y salario' },
  { id: 'proyectos', label: 'Proyectos' },
  { id: 'documentos', label: 'Documentos' },
  { id: 'descuentos', label: 'Descuentos', permission: 'payroll.view' },
  { id: 'comprobantes', label: 'Comprobantes', permission: 'payroll.view' },
] as const

type TabId = (typeof TABS)[number]['id']

const label = (items: [string, string][], value?: string | null) =>
  items.find(([v]) => v === value)?.[1]

function Item({ term, children }: { term: string; children: ReactNode }) {
  return (
    <div className="space-y-0.5">
      <dt className="text-muted-foreground text-xs">{term}</dt>
      <dd className="text-sm">{children || '—'}</dd>
    </div>
  )
}

function PersonalData({ e }: { e: Employee }) {
  const groups: { title: string; items: [string, ReactNode][] }[] = [
    {
      title: 'Identificación',
      items: [
        [e.id_type === 'passport' ? 'Pasaporte' : 'Cédula', e.id_number],
        ['Nº de seguro social', e.css_number],
        ['Nacionalidad', e.nationality],
        ['Fecha de nacimiento', e.birth_date ? formatDate(e.birth_date) : null],
        ['Sexo', e.sex === 'M' ? 'Masculino' : e.sex === 'F' ? 'Femenino' : null],
        ['Estado civil', label(MARITAL_STATUS, e.marital_status)],
      ],
    },
    {
      title: 'Contacto',
      items: [
        ['Teléfono', e.phone],
        ['Correo', e.email],
        ['Provincia', label(PROVINCES, e.province)],
        ['Dirección', e.address],
        [
          'Emergencia',
          e.emergency_contact_name &&
            `${e.emergency_contact_name}${e.emergency_contact_phone ? ` · ${e.emergency_contact_phone}` : ''}`,
        ],
      ],
    },
    {
      title: 'Empleo y pago',
      items: [
        ['Fecha de ingreso', formatDate(e.hire_date)],
        ['Fecha de salida', e.termination_date ? formatDate(e.termination_date) : null],
        ['Forma de pago', e.payment_method_display],
        ...(e.bank_display !== undefined
          ? ([
              ['Banco', e.bank_display],
              [
                'Cuenta',
                e.account_number &&
                  `${e.account_type === 'checking' ? 'Corriente' : 'Ahorros'} · ${e.account_number}`,
              ],
            ] as [string, ReactNode][])
          : []),
        ['Sindicato', e.is_union_member ? 'Afiliado (cuota sindical)' : 'No afiliado'],
      ],
    },
  ]
  return (
    <div className="grid gap-4 lg:grid-cols-3">
      {groups.map((g) => (
        <Card key={g.title}>
          <CardHeader>
            <CardTitle>{g.title}</CardTitle>
          </CardHeader>
          <CardContent>
            <dl className="space-y-3">
              {g.items.map(([term, value]) => (
                <Item key={term} term={term}>
                  {value}
                </Item>
              ))}
            </dl>
          </CardContent>
        </Card>
      ))}
      {e.notes && (
        <Card className="lg:col-span-3">
          <CardHeader>
            <CardTitle>Observaciones</CardTitle>
          </CardHeader>
          <CardContent className="text-sm whitespace-pre-line">{e.notes}</CardContent>
        </Card>
      )}
    </div>
  )
}

export function EmployeeDetailPage() {
  const { id = '' } = useParams()
  const { can } = useAccess()
  const [tab, setTab] = useState<TabId>('datos')
  const [editing, setEditing] = useState(false)
  const query = useHrEmployeesRetrieve(id)
  const e = query.data

  if (query.isPending) return <LoadingBlock />
  if (!e)
    return (
      <div className="mx-auto max-w-6xl space-y-4">
        <Alert>No se encontró el empleado o no tienes acceso a su expediente.</Alert>
        <Link to="/empleados" className="text-primary text-sm hover:underline">
          Volver a empleados
        </Link>
      </div>
    )

  const st = EMPLOYEE_STATUS[e.status]
  const initials = `${e.first_name[0] ?? ''}${e.last_name[0] ?? ''}`.toUpperCase()
  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <Link
        to="/empleados"
        className="text-muted-foreground hover:text-foreground inline-flex items-center gap-1 text-sm"
      >
        <ArrowLeft className="size-4" /> Empleados
      </Link>
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex items-center gap-4">
          <div className="bg-primary/10 text-primary flex size-14 items-center justify-center rounded-full text-lg font-semibold">
            {initials}
          </div>
          <div className="space-y-1">
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="text-2xl font-semibold tracking-tight">{e.full_name}</h1>
              <Badge variant={st.variant}>{st.label}</Badge>
            </div>
            <p className="text-muted-foreground text-sm">
              <span className="font-mono">{e.code}</span> · {e.id_number}
              {e.current_position && <> · {e.current_position}</>}
              {e.current_projects.length > 0 && (
                <> · {e.current_projects.map((p) => p.code).join(', ')}</>
              )}
            </p>
          </div>
        </div>
        {can('hr.employee.manage') && (
          <Button variant="outline" onClick={() => setEditing(true)}>
            <Pencil className="size-4" /> Editar datos
          </Button>
        )}
      </div>

      <div
        role="tablist"
        aria-label="Expediente"
        className="flex gap-1 overflow-x-auto overflow-y-hidden border-b"
      >
        {TABS.filter((t) => !('permission' in t) || can(t.permission)).map((t) => (
          <button
            key={t.id}
            role="tab"
            type="button"
            aria-selected={tab === t.id}
            onClick={() => setTab(t.id)}
            className={cn(
              'border-b-2 px-3 py-2 text-sm font-medium whitespace-nowrap transition-colors',
              tab === t.id
                ? 'border-primary text-foreground'
                : 'text-muted-foreground hover:text-foreground border-transparent',
            )}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div role="tabpanel">
        {tab === 'datos' && <PersonalData e={e} />}
        {tab === 'contratos' && <ContractsTab employee={e} />}
        {tab === 'proyectos' && <AssignmentsTab employee={e} />}
        {tab === 'documentos' && <DocumentsTab employee={e} />}
        {tab === 'descuentos' && <DeductionsTab employee={e} />}
        {tab === 'comprobantes' && <PayslipsTab employee={e} />}
      </div>
      {editing && <EmployeeDialog employee={e} onClose={() => setEditing(false)} />}
    </div>
  )
}
