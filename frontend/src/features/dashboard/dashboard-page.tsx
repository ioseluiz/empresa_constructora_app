import { useQuery } from '@tanstack/react-query'
import { apiGet } from '@/api/client'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'

interface Health {
  status: string
  database: string
}

export function DashboardPage() {
  const health = useQuery({
    queryKey: ['health'],
    queryFn: () => apiGet<Health>('/health/'),
    retry: false,
  })

  const apiOk = health.data?.status === 'ok'

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Inicio</h1>
        <p className="text-muted-foreground text-sm">
          Resumen de la empresa. Los indicadores de planilla aparecerán aquí.
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
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
