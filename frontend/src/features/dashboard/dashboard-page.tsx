import { useQuery } from '@tanstack/react-query'
import { api } from '@/api/client'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { useProjectsList } from '@/api/generated/proyectos/proyectos'
import { useAccess } from '@/features/access/use-access'
import { useAuth } from '@/features/auth/use-auth'
import { Link } from 'react-router-dom'

interface Health {
  status: string
  database: string
}

interface Tenant {
  id: string
  name: string
  legal_name: string
  ruc: string
  dv: string
}

export function DashboardPage() {
  const { user, currentTenant } = useAuth()
  const health = useQuery({
    queryKey: ['health'],
    queryFn: () => api.get<Health>('/health/', { anonymous: true }),
    retry: false,
  })
  const tenant = useQuery({
    queryKey: ['tenant', currentTenant?.tenant_id],
    queryFn: () => api.get<Tenant>('/tenant/current/'),
    enabled: !!currentTenant,
  })

  const { can } = useAccess()
  const activeProjects = useProjectsList(
    { status: 'active' },
    { query: { enabled: !!currentTenant && can('projects.view') } },
  )
  const apiOk = health.data?.status === 'ok'
  const firstName = user?.first_name || user?.full_name

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Hola, {firstName}</h1>
        <p className="text-muted-foreground text-sm">
          Resumen de la empresa. Los indicadores de planilla aparecerán aquí.
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle>Empresa</CardTitle>
          </CardHeader>
          <CardContent className="space-y-0.5">
            <p className="font-semibold">{tenant.data?.legal_name || currentTenant?.tenant_name}</p>
            <p className="text-muted-foreground text-sm">
              {tenant.data?.ruc
                ? `RUC ${tenant.data.ruc}${tenant.data.dv ? ` DV ${tenant.data.dv}` : ''}`
                : 'RUC sin registrar'}
            </p>
          </CardContent>
        </Card>
        {can('projects.view') && (
          <Card>
            <CardHeader>
              <CardTitle>Proyectos en ejecución</CardTitle>
            </CardHeader>
            <CardContent className="flex items-end justify-between">
              <p className="text-3xl font-semibold tabular-nums">
                {activeProjects.data?.count ?? '—'}
              </p>
              <Link to="/proyectos" className="text-primary text-sm font-medium hover:underline">
                Ver proyectos
              </Link>
            </CardContent>
          </Card>
        )}
        <Card>
          <CardHeader>
            <CardTitle>Estado del sistema</CardTitle>
          </CardHeader>
          <CardContent>
            {health.isPending ? (
              <Badge>Verificando…</Badge>
            ) : (
              <Badge variant={apiOk ? 'success' : 'danger'}>
                <span className="size-1.5 rounded-full bg-current" />
                {apiOk ? 'API operativa' : 'API no disponible'}
              </Badge>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
