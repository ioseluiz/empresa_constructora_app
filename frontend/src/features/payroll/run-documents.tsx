import { useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, Download, FileArchive, Landmark, Mail, RefreshCw } from 'lucide-react'
import { useState } from 'react'
import { downloadFile } from '@/api/client'
import type { PayrollRun } from '@/api/generated/model'
import {
  getPayrollRunsAchFileRetrieveUrl,
  getPayrollRunsPayslipsListQueryKey,
  getPayrollRunsPayslipsZipRetrieveUrl,
  usePayrollRunsAchRetrieve,
  usePayrollRunsPayslipsEmailCreate,
  usePayrollRunsPayslipsGenerateCreate,
  usePayrollRunsPayslipsList,
} from '@/api/generated/planilla/planilla'
import { Alert } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Dialog } from '@/components/ui/dialog'
import { useAccess } from '@/features/access/use-access'
import { formatMoney } from '@/lib/format'
import { useFormErrors } from '@/lib/use-form-errors'

const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`

/** Comprobantes de pago y archivo ACH de una planilla aprobada. */
export function RunDocuments({ run }: { run: PayrollRun }) {
  const queryClient = useQueryClient()
  const { can } = useAccess()
  const canReports = can('payroll.reports')
  // La emisión corre en segundo plano al aprobar: se consulta durante el primer minuto.
  const [openedAt] = useState(() => Date.now())
  const justApproved = !!run.approved_at && openedAt - new Date(run.approved_at).getTime() < 60_000
  const slips = usePayrollRunsPayslipsList(run.id, undefined, {
    query: {
      refetchInterval: (q) =>
        justApproved && (q.state.data?.length ?? 0) < run.employee_count ? 2000 : false,
    },
  })
  const ach = usePayrollRunsAchRetrieve(run.id, { query: { enabled: canReports } })
  const [confirmEmail, setConfirmEmail] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)
  const { error, reset, handle, setError } = useFormErrors()
  const generate = usePayrollRunsPayslipsGenerateCreate({
    mutation: {
      onSuccess: () =>
        void queryClient.invalidateQueries({
          queryKey: getPayrollRunsPayslipsListQueryKey(run.id),
        }),
      onError: handle,
    },
  })
  const email = usePayrollRunsPayslipsEmailCreate({
    mutation: {
      onSuccess: (r) => {
        setConfirmEmail(false)
        void queryClient.invalidateQueries({ queryKey: getPayrollRunsPayslipsListQueryKey(run.id) })
        setNotice(
          `Se enviaron ${r.sent} comprobantes.${r.missing_email.length ? ` Sin correo registrado: ${r.missing_email.join(', ')}.` : ''}`,
        )
      },
      onError: (e) => {
        setConfirmEmail(false)
        handle(e)
      },
    },
  })
  const download = (url: string, name: string) => {
    reset()
    downloadFile(url, name).catch((e: unknown) =>
      setError(e instanceof Error ? e.message : 'No se pudo descargar.'),
    )
  }
  const count = slips.data?.length ?? 0
  const pending = count < run.employee_count
  const withEmail = slips.data?.filter((s) => s.emailed_at).length ?? 0

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      {error && <Alert className="lg:col-span-2">{error}</Alert>}
      {notice && <p className="text-success text-sm lg:col-span-2">{notice}</p>}
      <Card>
        <CardContent className="space-y-3 pt-5">
          <div className="flex items-center gap-2">
            <FileArchive className="text-primary size-5" />
            <h2 className="font-semibold">Comprobantes de pago</h2>
          </div>
          <p className="text-muted-foreground text-sm">
            {pending
              ? justApproved
                ? `Emitiendo comprobantes… ${count} de ${run.employee_count}.`
                : `Faltan ${run.employee_count - count} de ${run.employee_count} comprobantes por emitir.`
              : `${plural(count, 'comprobante emitido', 'comprobantes emitidos')}${
                  withEmail ? ` · ${withEmail} enviados por correo` : ''
                }.`}
          </p>
          <div className="flex flex-wrap gap-2">
            <Button
              size="sm"
              variant="outline"
              disabled={count === 0}
              onClick={() =>
                download(
                  getPayrollRunsPayslipsZipRetrieveUrl(run.id),
                  `comprobantes_planilla_${run.number}.zip`,
                )
              }
            >
              <Download className="size-4" /> Descargar todos (ZIP)
            </Button>
            {canReports && (
              <Button
                size="sm"
                variant="outline"
                disabled={count === 0 || pending}
                onClick={() => setConfirmEmail(true)}
              >
                <Mail className="size-4" /> Enviar por correo
              </Button>
            )}
            {pending && !justApproved && can('payroll.approve') && (
              <Button
                size="sm"
                variant="ghost"
                loading={generate.isPending}
                onClick={() => generate.mutate({ id: run.id })}
              >
                <RefreshCw className="size-4" /> Emitir pendientes
              </Button>
            )}
          </div>
        </CardContent>
      </Card>

      {canReports && (
        <Card>
          <CardContent className="space-y-3 pt-5">
            <div className="flex items-center gap-2">
              <Landmark className="text-primary size-5" />
              <h2 className="font-semibold">Archivo de pago ACH</h2>
            </div>
            {ach.data ? (
              <>
                <p className="text-muted-foreground text-sm">
                  {plural(ach.data.rows.length, 'transferencia', 'transferencias')} por{' '}
                  {formatMoney(ach.data.total)}
                  {ach.data.non_ach.length > 0 &&
                    ` · ${ach.data.non_ach.length} pago(s) en cheque o efectivo por ${formatMoney(
                      ach.data.non_ach.reduce((s, n) => s + Number(n.amount), 0),
                    )}`}
                </p>
                {[...ach.data.blocking, ...ach.data.warnings].map((w) => (
                  <p key={w} className="flex items-start gap-2 text-xs">
                    <AlertTriangle className="text-danger mt-0.5 size-3.5 shrink-0" /> {w}
                  </p>
                ))}
                <Button
                  size="sm"
                  variant="outline"
                  disabled={ach.data.rows.length === 0 || ach.data.blocking.length > 0}
                  onClick={() =>
                    download(
                      getPayrollRunsAchFileRetrieveUrl(run.id),
                      `ach_planilla_${run.number}.csv`,
                    )
                  }
                >
                  <Download className="size-4" /> Descargar archivo (CSV genérico)
                </Button>
                <p className="text-muted-foreground text-xs">
                  Formato genérico. El formato específico de tu banco se agrega con su
                  especificación de carga.
                </p>
              </>
            ) : (
              <p className="text-muted-foreground text-sm">Cargando…</p>
            )}
          </CardContent>
        </Card>
      )}

      {confirmEmail && (
        <Dialog
          open
          onOpenChange={(o) => !o && setConfirmEmail(false)}
          title="Enviar comprobantes por correo"
          description={`Se enviará a cada empleado de la planilla #${run.number} su comprobante en PDF, al correo registrado en su expediente. Quienes no tengan correo se listarán al terminar.`}
          footer={
            <>
              <Button variant="outline" onClick={() => setConfirmEmail(false)}>
                Cancelar
              </Button>
              <Button loading={email.isPending} onClick={() => email.mutate({ id: run.id })}>
                Enviar
              </Button>
            </>
          }
        />
      )}
    </div>
  )
}
