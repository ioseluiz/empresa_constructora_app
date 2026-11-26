import { useQueryClient } from '@tanstack/react-query'
import {
  AlertTriangle,
  ArrowLeft,
  Banknote,
  Calculator,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Download,
  XCircle,
} from 'lucide-react'
import { Fragment, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { downloadFile } from '@/api/client'
import type { PayrollLine, Payslip } from '@/api/generated/model'
import {
  getPayrollPayslipsDownloadRetrieveUrl,
  getPayrollRunsLinesListQueryKey,
  getPayrollRunsListQueryKey,
  getPayrollRunsRetrieveQueryKey,
  getPayrollRunsSummaryRetrieveQueryKey,
  usePayrollRunsApproveCreate,
  usePayrollRunsCalculateCreate,
  usePayrollRunsCancelCreate,
  usePayrollRunsLinesList,
  usePayrollRunsPayCreate,
  usePayrollRunsPayslipsList,
  usePayrollRunsRetrieve,
  usePayrollRunsSummaryRetrieve,
} from '@/api/generated/planilla/planilla'
import { Alert } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Dialog } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { EmptyState, LoadingBlock } from '@/components/ui/page'
import { Pager } from '@/components/ui/pager'
import { Table, TBody, TD, TH, THead, TR } from '@/components/ui/table'
import { useAccess } from '@/features/access/use-access'
import { formatDate, formatDateTime, formatMoney } from '@/lib/format'
import { useFormErrors } from '@/lib/use-form-errors'
import { cn } from '@/lib/utils'
import { RUN_STATUS } from './constants'
import { RunDocuments } from './run-documents'

const KIND_LABEL: Record<string, string> = {
  earning: 'Ingreso',
  deduction: 'Deducción',
  employer: 'Aporte patronal',
  provision: 'Provisión',
}

function LineDetail({ line, payslip }: { line: PayrollLine; payslip?: Payslip }) {
  return (
    <div className="bg-muted/30 space-y-3 px-4 py-3">
      {payslip && (
        <Button
          size="sm"
          variant="outline"
          onClick={() =>
            void downloadFile(
              getPayrollPayslipsDownloadRetrieveUrl(payslip.id),
              `comprobante_${String(payslip.number).padStart(7, '0')}_${payslip.employee_code}.pdf`,
            )
          }
        >
          <Download className="size-4" /> Comprobante No. {String(payslip.number).padStart(7, '0')}
        </Button>
      )}
      {line.error && <Alert>{line.error}</Alert>}
      {line.warnings.length > 0 && (
        <ul className="space-y-1 text-sm">
          {line.warnings.map((w) => (
            <li key={w} className="flex gap-2">
              <AlertTriangle className="text-danger mt-0.5 size-4 shrink-0" /> {w}
            </li>
          ))}
        </ul>
      )}
      {line.items.length > 0 && (
        <table className="w-full text-sm">
          <thead className="text-muted-foreground text-xs">
            <tr>
              <th className="py-1 text-left font-medium">Concepto</th>
              <th className="py-1 text-left font-medium">Tipo</th>
              <th className="py-1 text-right font-medium">Cantidad</th>
              <th className="py-1 text-left font-medium">Centro de costo</th>
              <th className="py-1 text-left font-medium">Detalle</th>
              <th className="py-1 text-right font-medium">Monto</th>
            </tr>
          </thead>
          <tbody>
            {line.items.map((i) => (
              <tr key={i.id} className="border-t">
                <td className="py-1">{i.name}</td>
                <td className="text-muted-foreground py-1 text-xs">{KIND_LABEL[i.kind]}</td>
                <td className="py-1 text-right tabular-nums">{i.quantity ?? '—'}</td>
                <td className="text-muted-foreground py-1">{i.cost_center_code ?? '—'}</td>
                <td className="text-muted-foreground py-1 text-xs">{i.detail}</td>
                <td className="py-1 text-right tabular-nums">{formatMoney(i.amount)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {line.explanation.length > 0 && (
        <p className="text-muted-foreground text-xs">{line.explanation.join(' ')}</p>
      )}
    </div>
  )
}

type Confirm = 'approve' | 'cancel' | 'pay' | null

export function RunPage() {
  const { id = '' } = useParams()
  const queryClient = useQueryClient()
  const { can } = useAccess()
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const [expanded, setExpanded] = useState<string | null>(null)
  const [confirm, setConfirm] = useState<Confirm>(null)
  const { error, reset, handle } = useFormErrors()
  const run = usePayrollRunsRetrieve(id)
  const r = run.data
  const hasLines = !!r && r.status !== 'draft'
  const summary = usePayrollRunsSummaryRetrieve(id, { query: { enabled: hasLines } })
  const approvedRun = r?.status === 'approved' || r?.status === 'paid'
  const slips = usePayrollRunsPayslipsList(id, undefined, { query: { enabled: approvedRun } })
  const slipsByEmployee = new Map((slips.data ?? []).map((s) => [s.employee, s]))
  const lines = usePayrollRunsLinesList(
    id,
    { search: search || undefined, page },
    { query: { enabled: hasLines } },
  )
  const refresh = () => {
    for (const key of [
      getPayrollRunsRetrieveQueryKey(id),
      getPayrollRunsSummaryRetrieveQueryKey(id),
      getPayrollRunsLinesListQueryKey(id),
      getPayrollRunsListQueryKey(),
    ])
      void queryClient.invalidateQueries({ queryKey: key })
    setConfirm(null)
  }
  const opts = {
    mutation: {
      onSuccess: refresh,
      onError: (e: unknown) => {
        setConfirm(null)
        handle(e)
      },
    },
  }
  const calculate = usePayrollRunsCalculateCreate(opts)
  const approve = usePayrollRunsApproveCreate(opts)
  const pay = usePayrollRunsPayCreate(opts)
  const cancel = usePayrollRunsCancelCreate(opts)

  if (run.isPending) return <LoadingBlock />
  if (!r) return <Alert>No se encontró la planilla o no tienes acceso.</Alert>
  const st = RUN_STATUS[r.status]
  const editable = r.status === 'draft' || r.status === 'calculated'
  const canCalc = can('payroll.calculate')
  const canApprove = can('payroll.approve')

  const confirmations: Record<
    Exclude<Confirm, null>,
    {
      title: string
      text: string
      label: string
      danger?: boolean
      run: () => void
      loading: boolean
    }
  > = {
    approve: {
      title: 'Aprobar planilla',
      text: `Se aprobará la planilla #${r.number} por ${formatMoney(r.net)} netos a ${r.employee_count} ${r.employee_count === 1 ? 'empleado' : 'empleados'}. Las horas incluidas quedarán pagadas, los préstamos descontarán su saldo y la planilla ya no podrá modificarse.`,
      label: 'Aprobar',
      run: () => approve.mutate({ id }),
      loading: approve.isPending,
    },
    pay: {
      title: 'Marcar como pagada',
      text: 'Confirma que los pagos ya se realizaron (transferencias, cheques o efectivo).',
      label: 'Marcar pagada',
      run: () => pay.mutate({ id }),
      loading: pay.isPending,
    },
    cancel: {
      title: 'Anular planilla',
      text: 'La planilla quedará anulada y sus empleados podrán incluirse en otra planilla del período.',
      label: 'Anular',
      danger: true,
      run: () => cancel.mutate({ id }),
      loading: cancel.isPending,
    },
  }
  const dialog = confirm ? confirmations[confirm] : null

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <Link
        to="/planilla"
        className="text-muted-foreground hover:text-foreground inline-flex items-center gap-1 text-sm"
      >
        <ArrowLeft className="size-4" /> Planillas
      </Link>
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-semibold tracking-tight">
              Planilla #{r.number} · {r.scope === 'project' ? r.project_code : r.scope_display}
            </h1>
            <Badge variant={st.variant}>{st.label}</Badge>
          </div>
          <p className="text-muted-foreground text-sm">
            {r.frequency_display} · {formatDate(r.period_start)} – {formatDate(r.period_end)} · pago{' '}
            {formatDate(r.pay_date)}
            {r.approved_at &&
              ` · aprobada ${formatDateTime(r.approved_at)} por ${r.approved_by_email}`}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {editable && canCalc && (
            <Button variant="outline" onClick={() => setConfirm('cancel')}>
              <XCircle className="size-4" /> Anular
            </Button>
          )}
          {editable && canCalc && (
            <Button
              variant={r.status === 'calculated' ? 'outline' : 'primary'}
              loading={calculate.isPending}
              onClick={() => {
                reset()
                calculate.mutate({ id })
              }}
            >
              <Calculator className="size-4" />{' '}
              {r.status === 'calculated' ? 'Recalcular' : 'Calcular'}
            </Button>
          )}
          {r.status === 'calculated' && canApprove && (
            <Button
              disabled={r.error_count > 0 || r.employee_count === 0}
              onClick={() => {
                reset()
                setConfirm('approve')
              }}
            >
              <CheckCircle2 className="size-4" /> Aprobar
            </Button>
          )}
          {r.status === 'approved' && canApprove && (
            <Button
              onClick={() => {
                reset()
                setConfirm('pay')
              }}
            >
              <Banknote className="size-4" /> Marcar pagada
            </Button>
          )}
        </div>
      </div>
      {error && <Alert>{error}</Alert>}
      {r.notes && <Alert>{r.notes}</Alert>}
      {(r.status === 'approved' || r.status === 'paid') && <RunDocuments run={r} />}
      {r.status === 'draft' ? (
        <EmptyState
          icon={Calculator}
          title="Planilla en borrador"
          description="Calcúlala para ver a los empleados y sus montos."
        />
      ) : (
        <>
          <div className="grid gap-4 sm:grid-cols-5">
            {(
              [
                ['Empleados', String(r.employee_count)],
                ['Bruto', formatMoney(r.gross)],
                ['Deducciones', formatMoney(r.deductions)],
                ['Neto a pagar', formatMoney(r.net)],
                [
                  'Aportes y provisiones',
                  formatMoney(Number(r.employer_contributions) + Number(r.provisions)),
                ],
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

          {summary.data && summary.data.by_cost_center.length > 0 && (
            <section className="space-y-2">
              <h2 className="text-sm font-semibold">Costo por centro de costo</h2>
              <Table>
                <THead>
                  <tr>
                    <TH>Centro de costo</TH>
                    <TH className="text-right">Ingresos</TH>
                    <TH className="text-right">Aportes</TH>
                    <TH className="text-right">Provisiones</TH>
                    <TH className="text-right">Costo total</TH>
                  </tr>
                </THead>
                <TBody>
                  {summary.data.by_cost_center.map((c) => (
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
                    </TR>
                  ))}
                </TBody>
              </Table>
            </section>
          )}

          <section className="space-y-2">
            <div className="flex items-center justify-between gap-3">
              <h2 className="text-sm font-semibold">Empleados</h2>
              <Input
                type="search"
                placeholder="Buscar empleado…"
                aria-label="Buscar empleado"
                className="max-w-56"
                value={search}
                onChange={(e) => {
                  setSearch(e.target.value)
                  setPage(1)
                }}
              />
            </div>
            {lines.isPending ? (
              <LoadingBlock />
            ) : (lines.data?.results.length ?? 0) === 0 ? (
              <p className="text-muted-foreground text-sm">
                Ningún empleado en el alcance de esta planilla.
              </p>
            ) : (
              <>
                <Table>
                  <THead>
                    <tr>
                      <TH className="w-8" />
                      <TH>Empleado</TH>
                      <TH className="text-right">Bruto</TH>
                      <TH className="text-right">Deducciones</TH>
                      <TH className="text-right">Neto</TH>
                      <TH className="text-right">Costo empresa</TH>
                    </tr>
                  </THead>
                  <TBody>
                    {lines.data?.results.map((ln) => {
                      const open = expanded === ln.id
                      const flagged = !!ln.error || ln.warnings.length > 0
                      return (
                        <Fragment key={ln.id}>
                          <TR
                            className="cursor-pointer"
                            onClick={() => setExpanded(open ? null : ln.id)}
                          >
                            <TD>
                              {open ? (
                                <ChevronDown className="size-4" />
                              ) : (
                                <ChevronRight className="size-4" />
                              )}
                            </TD>
                            <TD>
                              <p className="flex items-center gap-1.5 font-medium">
                                {ln.employee_name}
                                {flagged && (
                                  <AlertTriangle
                                    className={cn(
                                      'size-4',
                                      ln.error ? 'text-danger' : 'text-muted-foreground',
                                    )}
                                    aria-label="Con observaciones"
                                  />
                                )}
                              </p>
                              <p className="text-muted-foreground font-mono text-xs">
                                {ln.employee_code} ·{' '}
                                {ln.pay_basis === 'monthly' ? 'Asalariado' : 'Por hora'}
                              </p>
                            </TD>
                            <TD className="text-right tabular-nums">{formatMoney(ln.gross)}</TD>
                            <TD className="text-right tabular-nums">
                              {formatMoney(ln.deductions)}
                            </TD>
                            <TD className="text-right font-medium tabular-nums">
                              {ln.error ? 'Error' : formatMoney(ln.net)}
                            </TD>
                            <TD className="text-right tabular-nums">
                              {formatMoney(
                                Number(ln.gross) +
                                  Number(ln.employer_contributions) +
                                  Number(ln.provisions),
                              )}
                            </TD>
                          </TR>
                          {open && (
                            <tr>
                              <td colSpan={6} className="p-0">
                                <LineDetail line={ln} payslip={slipsByEmployee.get(ln.employee)} />
                              </td>
                            </tr>
                          )}
                        </Fragment>
                      )
                    })}
                  </TBody>
                </Table>
                <Pager
                  total={lines.data?.count ?? 0}
                  page={page}
                  onPage={setPage}
                  noun={['empleado', 'empleados']}
                />
              </>
            )}
          </section>
        </>
      )}
      {dialog && (
        <Dialog
          open
          onOpenChange={(o) => !o && setConfirm(null)}
          title={dialog.title}
          description={dialog.text}
          footer={
            <>
              <Button variant="outline" onClick={() => setConfirm(null)}>
                Cancelar
              </Button>
              <Button
                variant={dialog.danger ? 'danger' : 'primary'}
                loading={dialog.loading}
                onClick={dialog.run}
              >
                {dialog.label}
              </Button>
            </>
          }
        />
      )}
    </div>
  )
}
