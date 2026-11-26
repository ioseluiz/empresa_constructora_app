import { Download, FileSpreadsheet, Info } from 'lucide-react'
import { useState } from 'react'
import { downloadFile } from '@/api/client'
import { getPayrollReportsSipeRetrieveUrl } from '@/api/generated/planilla/planilla'
import { Alert } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { PageHeader } from '@/components/ui/page'

function previousMonth() {
  const d = new Date()
  d.setDate(1)
  d.setMonth(d.getMonth() - 1)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
}

export function ReportsPage() {
  const [month, setMonth] = useState(previousMonth())
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const download = () => {
    setError(null)
    setLoading(true)
    downloadFile(
      getPayrollReportsSipeRetrieveUrl({ month }),
      `cuotas_css_se_${month.replace('-', '')}.xlsx`,
    )
      .catch((e: unknown) =>
        setError(e instanceof Error ? e.message : 'No se pudo generar el informe.'),
      )
      .finally(() => setLoading(false))
  }
  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <PageHeader
        title="Reportes"
        description="Informes legales generados a partir de las planillas aprobadas."
      />
      {error && <Alert>{error}</Alert>}
      <Card>
        <CardContent className="space-y-4 pt-5">
          <div className="flex items-start gap-3">
            <FileSpreadsheet className="text-primary mt-0.5 size-5" />
            <div className="space-y-1">
              <h2 className="font-semibold">Cuotas de Seguro Social y Seguro Educativo (SIPE)</h2>
              <p className="text-muted-foreground text-sm">
                Excel con la base y las cuotas de cada empleado (empleado, patronal y riesgos
                profesionales) de las planillas aprobadas con fecha de pago en el mes, más el ISR
                retenido.
              </p>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <label className="flex items-center gap-2 text-sm">
              Mes
              <Input
                type="month"
                value={month}
                onChange={(e) => setMonth(e.target.value)}
                className="w-44"
              />
            </label>
            <Button loading={loading} disabled={!month} onClick={download}>
              <Download className="size-4" /> Descargar Excel
            </Button>
          </div>
          <p className="text-muted-foreground flex items-start gap-2 text-xs">
            <Info className="mt-0.5 size-3.5 shrink-0" />
            Informe base para la declaración en el SIPE de la CSS: valida con tu contador el formato
            de carga vigente.
          </p>
        </CardContent>
      </Card>
    </div>
  )
}
