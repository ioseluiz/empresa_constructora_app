import { Download, FileText } from 'lucide-react'
import { downloadFile } from '@/api/client'
import type { Employee } from '@/api/generated/model'
import {
  getPayrollPayslipsDownloadRetrieveUrl,
  usePayrollPayslipsList,
} from '@/api/generated/planilla/planilla'
import { Button } from '@/components/ui/button'
import { EmptyState, LoadingBlock } from '@/components/ui/page'
import { Table, TBody, TD, TH, THead, TR } from '@/components/ui/table'
import { formatDate, formatDateTime, formatMoney } from '@/lib/format'

export function PayslipsTab({ employee }: { employee: Employee }) {
  const slips = usePayrollPayslipsList({ employee: employee.id })
  const rows = slips.data?.results ?? []
  if (slips.isPending) return <LoadingBlock />
  if (rows.length === 0)
    return (
      <EmptyState
        icon={FileText}
        title="Sin comprobantes"
        description="Se emiten al aprobar cada planilla."
      />
    )
  return (
    <Table>
      <THead>
        <tr>
          <TH>Comprobante</TH>
          <TH>Período</TH>
          <TH>Pago</TH>
          <TH className="text-right">Neto</TH>
          <TH>Enviado</TH>
          <TH className="w-12" />
        </tr>
      </THead>
      <TBody>
        {rows.map((s) => {
          const number = String(s.number).padStart(7, '0')
          return (
            <TR key={s.id}>
              <TD>
                <p className="font-mono">{number}</p>
                <p className="text-muted-foreground text-xs">Planilla #{s.run_number}</p>
              </TD>
              <TD className="whitespace-nowrap">
                {formatDate(s.period_start)} – {formatDate(s.period_end)}
              </TD>
              <TD className="whitespace-nowrap">{formatDate(s.pay_date)}</TD>
              <TD className="text-right font-medium tabular-nums">{formatMoney(s.net)}</TD>
              <TD className="text-muted-foreground text-xs">
                {s.emailed_at ? formatDateTime(s.emailed_at) : '—'}
              </TD>
              <TD>
                <Button
                  size="icon"
                  variant="ghost"
                  aria-label="Descargar comprobante"
                  onClick={() =>
                    void downloadFile(
                      getPayrollPayslipsDownloadRetrieveUrl(s.id),
                      `comprobante_${number}_${s.employee_code}.pdf`,
                    )
                  }
                >
                  <Download className="size-4" />
                </Button>
              </TD>
            </TR>
          )
        })}
      </TBody>
    </Table>
  )
}
