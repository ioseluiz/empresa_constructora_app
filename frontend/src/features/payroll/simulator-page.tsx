import { AlertTriangle, Calculator } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import type { PayLine, PreviewResult } from '@/api/generated/model'
import { usePayrollPreviewCreate } from '@/api/generated/planilla/planilla'
import { useHrEmployeesList } from '@/api/generated/personal/personal'
import { Alert } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { FormField } from '@/components/ui/form-field'
import { Input } from '@/components/ui/input'
import { EmptyState, PageHeader } from '@/components/ui/page'
import { Select } from '@/components/ui/select'
import { Table, TBody, TD, TH, THead, TR } from '@/components/ui/table'
import { useAccess } from '@/features/access/use-access'
import { formatMoney } from '@/lib/format'
import { useFormErrors } from '@/lib/use-form-errors'
import { PayrollTabs } from './payroll-tabs'

const pad = (n: number) => String(n).padStart(2, '0')
const iso = (d: Date) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`

function presets(): [string, string, string][] {
  const now = new Date()
  const monday = new Date(now)
  monday.setDate(now.getDate() - ((now.getDay() + 6) % 7) - 7)
  const sunday = new Date(monday)
  sunday.setDate(monday.getDate() + 6)
  const y = now.getFullYear()
  const m = now.getMonth()
  const firstHalf = now.getDate() <= 15
  const lastDay = new Date(y, m + 1, 0).getDate()
  return [
    ['Semana pasada', iso(monday), iso(sunday)],
    [
      'Quincena actual',
      `${y}-${pad(m + 1)}-${firstHalf ? '01' : '16'}`,
      `${y}-${pad(m + 1)}-${firstHalf ? '15' : String(lastDay)}`,
    ],
    ['Mes actual', `${y}-${pad(m + 1)}-01`, `${y}-${pad(m + 1)}-${lastDay}`],
  ]
}

function rateLabel(rate: string | null, percent: boolean) {
  if (!rate) return '—'
  if (percent) return `${(Number(rate) * 100).toFixed(2)} %`
  return formatMoney(rate, 4)
}

function LinesTable({
  title,
  lines,
  showCostCenter,
  percent = false,
}: {
  title: string
  lines: PayLine[]
  showCostCenter?: boolean
  percent?: boolean
}) {
  if (lines.length === 0) return null
  const total = lines.reduce((sum, ln) => sum + Number(ln.amount), 0)
  return (
    <section className="space-y-2">
      <h2 className="text-sm font-semibold">{title}</h2>
      <Table>
        <THead>
          <tr>
            <TH>Concepto</TH>
            <TH className="text-right">Cantidad</TH>
            <TH className="text-right">Tarifa</TH>
            {showCostCenter && <TH>Centro de costo</TH>}
            <TH>Detalle</TH>
            <TH className="text-right">Monto</TH>
          </tr>
        </THead>
        <TBody>
          {lines.map((ln, i) => (
            <TR key={`${ln.code}-${ln.cost_center}-${i}`}>
              <TD className="font-medium">{ln.name}</TD>
              <TD className="text-right tabular-nums">{ln.quantity ?? '—'}</TD>
              <TD className="text-right tabular-nums">{rateLabel(ln.rate, percent)}</TD>
              {showCostCenter && <TD className="text-muted-foreground">{ln.cost_center ?? '—'}</TD>}
              <TD className="text-muted-foreground text-xs">{ln.detail}</TD>
              <TD className="text-right font-medium tabular-nums">{formatMoney(ln.amount)}</TD>
            </TR>
          ))}
          <TR>
            <TD className="font-semibold" colSpan={showCostCenter ? 5 : 4}>
              Total
            </TD>
            <TD className="text-right font-semibold tabular-nums">{formatMoney(total)}</TD>
          </TR>
        </TBody>
      </Table>
    </section>
  )
}

export function SimulatorPage() {
  const { can } = useAccess()
  const [search, setSearch] = useState('')
  const [employee, setEmployee] = useState('')
  const options = presets()
  const [period, setPeriod] = useState({ start: options[0][1], end: options[0][2] })
  const [result, setResult] = useState<PreviewResult | null>(null)
  const employees = useHrEmployeesList({
    status: 'active',
    search: search || undefined,
    ordering: 'last_name',
  })
  const { errors, error, reset, handle } = useFormErrors()
  const preview = usePayrollPreviewCreate({ mutation: { onSuccess: setResult, onError: handle } })
  const submit = (e: FormEvent) => {
    e.preventDefault()
    reset()
    setResult(null)
    preview.mutate({ data: { employee, period_start: period.start, period_end: period.end } })
  }
  const by = (kind: string) => result?.lines.filter((ln) => ln.kind === kind) ?? []

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <PageHeader
        title="Planilla"
        description="Simula el pago de un empleado con sus horas aprobadas, salario, descuentos y las reglas de Panamá. No guarda nada."
      />
      <PayrollTabs />
      {!can('payroll.calculate') ? (
        <Alert>Necesitas el permiso para calcular planillas para usar el simulador.</Alert>
      ) : (
        <form
          onSubmit={submit}
          className="bg-card grid gap-4 rounded-lg border p-4 md:grid-cols-[1fr_auto_auto_auto] md:items-end"
        >
          <FormField id="sim-employee" label="Empleado" error={errors.employee}>
            <div className="flex gap-2">
              <Input
                type="search"
                aria-label="Buscar empleado"
                placeholder="Buscar…"
                className="max-w-40"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
              <Select
                id="sim-employee"
                className="w-full"
                required
                value={employee}
                onChange={(e) => setEmployee(e.target.value)}
              >
                <option value="">Selecciona…</option>
                {employees.data?.results.map((e) => (
                  <option key={e.id} value={e.id}>
                    {e.full_name} · {e.code}
                  </option>
                ))}
              </Select>
            </div>
          </FormField>
          <FormField id="sim-start" label="Desde" error={errors.period_start}>
            <Input
              id="sim-start"
              type="date"
              required
              value={period.start}
              onChange={(e) => setPeriod({ ...period, start: e.target.value })}
            />
          </FormField>
          <FormField id="sim-end" label="Hasta" error={errors.period_end}>
            <Input
              id="sim-end"
              type="date"
              required
              value={period.end}
              onChange={(e) => setPeriod({ ...period, end: e.target.value })}
            />
          </FormField>
          <Button type="submit" loading={preview.isPending}>
            <Calculator className="size-4" /> Calcular
          </Button>
          <div className="flex flex-wrap gap-1 md:col-span-4">
            {options.map(([label, start, end]) => (
              <Button
                key={label}
                type="button"
                size="sm"
                variant={period.start === start && period.end === end ? 'outline' : 'ghost'}
                onClick={() => setPeriod({ start, end })}
              >
                {label}
              </Button>
            ))}
          </div>
        </form>
      )}
      {error && <Alert>{error}</Alert>}
      {!result && !error && can('payroll.calculate') && (
        <EmptyState
          icon={Calculator}
          title="Elige un empleado y un período"
          description="Solo se incluyen las horas de jornadas aprobadas."
        />
      )}
      {result && (
        <div className="space-y-6">
          <div className="grid gap-4 sm:grid-cols-4">
            {(
              [
                ['Salario bruto', result.gross],
                ['Deducciones', result.deductions],
                ['Neto a pagar', result.net],
                ['Costo para la empresa', result.employer_cost],
              ] as const
            ).map(([label, value]) => (
              <Card key={label}>
                <CardHeader>
                  <CardTitle>{label}</CardTitle>
                </CardHeader>
                <CardContent className="text-2xl font-semibold tabular-nums">
                  {formatMoney(value)}
                </CardContent>
              </Card>
            ))}
          </div>
          {result.warnings.length > 0 && (
            <div className="border-danger/30 bg-danger/5 space-y-1 rounded-md border p-3 text-sm">
              {result.warnings.map((w) => (
                <p key={w} className="flex items-start gap-2">
                  <AlertTriangle className="text-danger mt-0.5 size-4 shrink-0" /> {w}
                </p>
              ))}
            </div>
          )}
          <LinesTable title="Ingresos" lines={by('earning')} showCostCenter />
          <LinesTable title="Deducciones del empleado" lines={by('deduction')} percent />
          <LinesTable title="Aportes patronales" lines={by('employer')} showCostCenter percent />
          <LinesTable title="Provisiones" lines={by('provision')} showCostCenter percent />
          {result.explanation.length > 0 && (
            <ul className="text-muted-foreground list-inside list-disc text-sm">
              {result.explanation.map((x) => (
                <li key={x}>{x}</li>
              ))}
            </ul>
          )}
          <details className="text-sm">
            <summary className="text-muted-foreground cursor-pointer">
              Parámetros legales usados
            </summary>
            <dl className="mt-2 grid gap-1 sm:grid-cols-2">
              {Object.entries(result.parameters).map(([k, v]) => (
                <div key={k} className="flex justify-between gap-4 border-b py-1">
                  <dt className="font-mono text-xs">{k}</dt>
                  <dd className="text-muted-foreground text-xs">{v}</dd>
                </div>
              ))}
            </dl>
          </details>
        </div>
      )}
    </div>
  )
}
