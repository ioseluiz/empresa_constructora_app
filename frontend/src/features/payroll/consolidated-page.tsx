import { Layers } from 'lucide-react'
import { useState } from 'react'
import { usePayrollConsolidatedRetrieve } from '@/api/generated/planilla/planilla'
import { Alert } from '@/components/ui/alert'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { EmptyState, LoadingBlock, PageHeader } from '@/components/ui/page'
import { Table, TBody, TD, TH, THead, TR } from '@/components/ui/table'
import { useAccess } from '@/features/access/use-access'
import { formatMoney } from '@/lib/format'
import { isoDate } from './constants'
import { PayrollTabs } from './payroll-tabs'

const KINDS: [string, string][] = [
  ['earning', 'Ingresos'],
  ['deduction', 'Deducciones'],
  ['employer', 'Aportes patronales'],
  ['provision', 'Provisiones'],
]

function currentMonth() {
  const now = new Date()
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`
}

export function ConsolidatedPage() {
  const { isOwner, can } = useAccess()
  const [month, setMonth] = useState(currentMonth())
  const [includeCalculated, setIncludeCalculated] = useState(false)
  const [y, m] = month.split('-').map(Number)
  const params = {
    date_from: isoDate(new Date(y, m - 1, 1)),
    date_to: isoDate(new Date(y, m, 0)),
    include_calculated: includeCalculated || undefined,
  }
  const data = usePayrollConsolidatedRetrieve(params, { query: { enabled: !!month, retry: false } })
  const d = data.data
  const totalCost = d ? d.by_cost_center.reduce((s, c) => s + Number(c.total_cost), 0) : 0

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <PageHeader
        title="Planilla"
        description="Planilla global: todas las planillas con fecha de pago en el mes, consolidadas por centro de costo y por concepto."
      />
      <PayrollTabs />
      <div className="flex flex-wrap items-center gap-4">
        <label className="flex items-center gap-2 text-sm">
          Mes de pago
          <Input
            type="month"
            value={month}
            onChange={(e) => setMonth(e.target.value)}
            className="w-44"
          />
        </label>
        <label className="flex items-center gap-2 text-sm">
          <Checkbox
            checked={includeCalculated}
            onChange={(e) => setIncludeCalculated(e.target.checked)}
          />
          Incluir planillas calculadas sin aprobar
        </label>
      </div>
      {!isOwner && !can('payroll.view') ? null : data.isPending ? (
        <LoadingBlock />
      ) : data.error ? (
        <Alert>La planilla global requiere acceso a toda la empresa.</Alert>
      ) : !d || d.runs === 0 ? (
        <EmptyState
          icon={Layers}
          title="Sin planillas en el mes"
          description="Solo se consolidan las planillas aprobadas o pagadas."
        />
      ) : (
        <div className="space-y-6">
          <div className="grid gap-4 sm:grid-cols-5">
            {(
              [
                ['Planillas', String(d.runs)],
                ['Empleados', String(d.employees)],
                ['Bruto', formatMoney(d.totals.gross)],
                ['Neto pagado', formatMoney(d.totals.net)],
                ['Costo total', formatMoney(totalCost)],
              ] as const
            ).map(([label, value]) => (
              <Card key={label}>
                <CardHeader>
                  <CardTitle>{label}</CardTitle>
                </CardHeader>
                <CardContent className="text-xl font-semibold tabular-nums">{value}</CardContent>
              </Card>
            ))}
          </div>
          <section className="space-y-2">
            <h2 className="text-sm font-semibold">Por centro de costo</h2>
            <Table>
              <THead>
                <tr>
                  <TH>Centro de costo</TH>
                  <TH className="text-right">Ingresos</TH>
                  <TH className="text-right">Aportes</TH>
                  <TH className="text-right">Provisiones</TH>
                  <TH className="text-right">Costo total</TH>
                  <TH className="text-right">% del total</TH>
                </tr>
              </THead>
              <TBody>
                {d.by_cost_center.map((c) => (
                  <TR key={c.cost_center}>
                    <TD>
                      <span className="font-mono text-xs">{c.cost_center}</span> {c.name}
                    </TD>
                    <TD className="text-right tabular-nums">{formatMoney(c.earning)}</TD>
                    <TD className="text-right tabular-nums">{formatMoney(c.employer)}</TD>
                    <TD className="text-right tabular-nums">{formatMoney(c.provision)}</TD>
                    <TD className="text-right font-medium tabular-nums">
                      {formatMoney(c.total_cost)}
                    </TD>
                    <TD className="text-muted-foreground text-right tabular-nums">
                      {totalCost ? ((Number(c.total_cost) / totalCost) * 100).toFixed(1) : '0'} %
                    </TD>
                  </TR>
                ))}
              </TBody>
            </Table>
          </section>
          <div className="grid gap-6 lg:grid-cols-2">
            {KINDS.map(([kind, title]) => {
              const rows = d.by_concept.filter((c) => c.kind === kind)
              if (rows.length === 0) return null
              return (
                <section key={kind} className="space-y-2">
                  <h2 className="text-sm font-semibold">{title}</h2>
                  <Table>
                    <TBody>
                      {rows.map((c) => (
                        <TR key={c.code}>
                          <TD>{c.name}</TD>
                          <TD className="text-right tabular-nums">{formatMoney(c.total)}</TD>
                        </TR>
                      ))}
                    </TBody>
                  </Table>
                </section>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}
