import { Info } from 'lucide-react'
import type { LegalParameter } from '@/api/generated/model'
import { usePayrollLegalParametersList } from '@/api/generated/planilla/planilla'
import { Badge } from '@/components/ui/badge'
import { LoadingBlock, PageHeader } from '@/components/ui/page'
import { Table, TBody, TD, TH, THead, TR } from '@/components/ui/table'
import { todayISO } from '@/features/employees/constants'
import { formatDate, formatMoney } from '@/lib/format'
import { PayrollTabs } from './payroll-tabs'

type Bracket = { from: number; to: number | null; rate: string; fixed: string }

const PERCENT_KEYS = /rate$|^surcharge_/

function Value({ p }: { p: LegalParameter }) {
  if (p.key === 'isr_brackets' && Array.isArray(p.table)) {
    return (
      <ul className="space-y-0.5 text-xs">
        {(p.table as Bracket[]).map((b) => (
          <li key={b.from}>
            {b.to
              ? `De ${formatMoney(b.from)} a ${formatMoney(b.to)}`
              : `Más de ${formatMoney(b.from)}`}
            :{' '}
            {Number(b.rate) === 0
              ? 'exento'
              : `${Number(b.fixed) ? `${formatMoney(b.fixed)} + ` : ''}${Number(b.rate) * 100} % sobre el excedente`}
          </li>
        ))}
      </ul>
    )
  }
  if (p.value === null || p.value === undefined) return <span>—</span>
  return PERCENT_KEYS.test(p.key) ? (
    <span className="font-medium tabular-nums">
      {(Number(p.value) * 100).toFixed(4).replace(/\.?0+$/, '')} %
    </span>
  ) : (
    <span className="font-medium tabular-nums">{Number(p.value)}</span>
  )
}

export function ParametersPage() {
  const params = usePayrollLegalParametersList({ country: 'PA' })
  const today = todayISO()
  const rows = params.data ?? []
  // El vigente de cada clave es el de fecha más reciente que ya empezó.
  const current = new Set(
    Object.values(
      rows
        .filter((p) => p.valid_from <= today)
        .reduce<Record<string, LegalParameter>>((acc, p) => {
          if (!acc[p.key] || acc[p.key].valid_from < p.valid_from) acc[p.key] = p
          return acc
        }, {}),
    ).map((p) => p.id),
  )

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <PageHeader
        title="Planilla"
        description="Tasas, tablas y recargos de Panamá con su fecha de vigencia."
      />
      <PayrollTabs />
      <div className="bg-primary/5 flex gap-3 rounded-md border p-4 text-sm">
        <Info className="text-primary mt-0.5 size-4 shrink-0" />
        <p>
          Los administra la plataforma para todas las empresas. Cuando cambia una tasa (por ejemplo,
          los aumentos escalonados de la cuota patronal de la Ley 462 de 2025) se carga una vigencia
          nueva y las planillas de fechas anteriores no cambian. Son valores de referencia:
          valídalos con tu contador.
        </p>
      </div>
      {params.isPending ? (
        <LoadingBlock />
      ) : (
        <Table>
          <THead>
            <tr>
              <TH>Parámetro</TH>
              <TH>Valor</TH>
              <TH>Vigente desde</TH>
              <TH>Base legal / notas</TH>
            </tr>
          </THead>
          <TBody>
            {rows.map((p) => (
              <TR key={p.id} className={current.has(p.id) ? undefined : 'opacity-60'}>
                <TD>
                  <p className="font-medium">{p.name}</p>
                  <p className="text-muted-foreground font-mono text-xs">{p.key}</p>
                </TD>
                <TD>
                  <Value p={p} />
                </TD>
                <TD className="whitespace-nowrap">
                  {formatDate(p.valid_from)}
                  {current.has(p.id) ? (
                    <Badge className="ml-2" variant="success">
                      Vigente
                    </Badge>
                  ) : p.valid_from > today ? (
                    <Badge className="ml-2">Futuro</Badge>
                  ) : null}
                </TD>
                <TD className="text-muted-foreground max-w-80 text-xs">
                  {[p.legal_basis, p.notes].filter(Boolean).join(' · ') || '—'}
                </TD>
              </TR>
            ))}
          </TBody>
        </Table>
      )}
    </div>
  )
}
