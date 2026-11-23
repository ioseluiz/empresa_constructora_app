import { useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, CheckCircle2, Loader2, Undo2 } from 'lucide-react'
import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import type { TimeclockBatchesRowsRetrieveRowStatus } from '@/api/generated/model'
import {
  getTimeclockBatchesListQueryKey,
  getTimeclockBatchesRetrieveQueryKey,
  getTimeclockBatchesRowsRetrieveQueryKey,
  getTimeclockPunchesListQueryKey,
  useTimeclockBatchesConfirmCreate,
  useTimeclockBatchesDiscardCreate,
  useTimeclockBatchesRetrieve,
  useTimeclockBatchesRevertCreate,
  useTimeclockBatchesRowsRetrieve,
} from '@/api/generated/marcaciones/marcaciones'
import { Alert } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Dialog } from '@/components/ui/dialog'
import { FormField } from '@/components/ui/form-field'
import { Input } from '@/components/ui/input'
import { LoadingBlock } from '@/components/ui/page'
import { Pager } from '@/components/ui/pager'
import { Table, TBody, TD, TH, THead, TR } from '@/components/ui/table'
import { formatDateTime, formatDay, formatTime } from '@/lib/format'
import { useFormErrors } from '@/lib/use-form-errors'
import { cn } from '@/lib/utils'
import { BATCH_STATUS } from './constants'

const FILTERS = [
  ['', 'Todas'],
  ['valid', 'Válidas'],
  ['error', 'Con error'],
  ['duplicate', 'Duplicadas'],
] as const

const DIRECTION_LABEL: Record<string, string> = {
  in: 'Entrada',
  out: 'Salida',
  unknown: 'Sin tipo',
}

export function BatchPage() {
  const { id = '' } = useParams()
  const queryClient = useQueryClient()
  const [rowStatus, setRowStatus] = useState('')
  const [page, setPage] = useState(1)
  const [reverting, setReverting] = useState(false)
  const [reason, setReason] = useState('')
  const { error, reset, handle } = useFormErrors()
  const batch = useTimeclockBatchesRetrieve(id, {
    query: {
      refetchInterval: (q) =>
        q.state.data && ['pending', 'processing'].includes(q.state.data.status) ? 1500 : false,
    },
  })
  const b = batch.data
  const ready = !!b && !['pending', 'processing'].includes(b.status)
  const rows = useTimeclockBatchesRowsRetrieve(
    id,
    {
      row_status: (rowStatus || undefined) as TimeclockBatchesRowsRetrieveRowStatus | undefined,
      page,
    },
    { query: { enabled: ready && b?.status !== 'failed' } },
  )
  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: getTimeclockBatchesRetrieveQueryKey(id) })
    void queryClient.invalidateQueries({ queryKey: getTimeclockBatchesRowsRetrieveQueryKey(id) })
    void queryClient.invalidateQueries({ queryKey: getTimeclockBatchesListQueryKey() })
    void queryClient.invalidateQueries({ queryKey: getTimeclockPunchesListQueryKey() })
  }
  const options = { mutation: { onSuccess: refresh, onError: handle } }
  const confirm = useTimeclockBatchesConfirmCreate(options)
  const discard = useTimeclockBatchesDiscardCreate(options)
  const revert = useTimeclockBatchesRevertCreate({
    mutation: {
      onSuccess: () => {
        refresh()
        setReverting(false)
      },
      onError: handle,
    },
  })

  if (batch.isPending) return <LoadingBlock />
  if (!b) return <Alert>No se encontró la importación.</Alert>
  const st = BATCH_STATUS[b.status]

  const stats: [string, number, string?][] = [
    ['Filas leídas', b.total_rows],
    ['Válidas', b.valid_rows, 'text-success'],
    ['Con error', b.error_rows, b.error_rows ? 'text-danger' : undefined],
    ['Duplicadas', b.duplicate_rows],
  ]

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <Link
        to="/marcaciones/importaciones"
        className="text-muted-foreground hover:text-foreground inline-flex items-center gap-1 text-sm"
      >
        <ArrowLeft className="size-4" /> Importaciones
      </Link>
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-semibold tracking-tight">{b.original_name}</h1>
            <Badge variant={st.variant}>{st.label}</Badge>
          </div>
          <p className="text-muted-foreground text-sm">
            {b.source_display}
            {b.device_name && ` · ${b.device_name}`}
            {b.template_name && ` · ${b.template_name}`}
            {b.project_code && ` · ${b.project_code}`} · subido {formatDateTime(b.created_at)}
          </p>
        </div>
        <div className="flex gap-2">
          {b.status === 'preview' && (
            <>
              <Button
                variant="outline"
                loading={discard.isPending}
                onClick={() => {
                  reset()
                  discard.mutate({ id })
                }}
              >
                Descartar
              </Button>
              <Button
                disabled={b.valid_rows === 0}
                loading={confirm.isPending}
                onClick={() => {
                  reset()
                  confirm.mutate({ id })
                }}
              >
                <CheckCircle2 className="size-4" /> Confirmar {b.valid_rows} marcaciones
              </Button>
            </>
          )}
          {b.status === 'confirmed' && (
            <Button variant="outline" onClick={() => setReverting(true)}>
              <Undo2 className="size-4" /> Revertir lote
            </Button>
          )}
        </div>
      </div>
      {error && <Alert>{error}</Alert>}

      {!ready ? (
        <Card>
          <CardContent className="text-muted-foreground flex items-center gap-3 pt-5 text-sm">
            <Loader2 className="size-4 animate-spin" /> Analizando el archivo…
          </CardContent>
        </Card>
      ) : b.status === 'failed' ? (
        <Alert>{b.error}</Alert>
      ) : (
        <>
          <div className="grid gap-4 sm:grid-cols-4">
            {stats.map(([label, value, color]) => (
              <Card key={label}>
                <CardHeader>
                  <CardTitle>{label}</CardTitle>
                </CardHeader>
                <CardContent className={cn('text-2xl font-semibold tabular-nums', color)}>
                  {value}
                </CardContent>
              </Card>
            ))}
          </div>
          {b.status === 'confirmed' && (
            <p className="text-muted-foreground text-sm">
              Confirmado {formatDateTime(b.confirmed_at)}: {b.punch_count} marcaciones vigentes
              {b.first_punch && ` del ${formatDay(b.first_punch)} al ${formatDay(b.last_punch)}`}.
            </p>
          )}
          {b.status === 'reverted' && (
            <Alert>
              Revertido {formatDateTime(b.reverted_at)}: {b.revert_reason}. Sus marcaciones quedaron
              anuladas.
            </Alert>
          )}
          <div className="flex gap-1">
            {FILTERS.map(([value, label]) => (
              <Button
                key={value}
                size="sm"
                variant={rowStatus === value ? 'primary' : 'ghost'}
                onClick={() => {
                  setRowStatus(value)
                  setPage(1)
                }}
              >
                {label}
              </Button>
            ))}
          </div>
          {rows.isPending ? (
            <LoadingBlock />
          ) : (
            <>
              <Table>
                <THead>
                  <tr>
                    <TH className="w-16">Fila</TH>
                    <TH>Empleado</TH>
                    <TH>Fecha</TH>
                    <TH>Hora</TH>
                    <TH>Tipo</TH>
                    <TH>Resultado</TH>
                  </tr>
                </THead>
                <TBody>
                  {rows.data?.results.map((r) => (
                    <TR key={r.id}>
                      <TD className="text-muted-foreground tabular-nums">{r.row_number}</TD>
                      <TD>
                        {r.employee_name ? (
                          <>
                            <p className="font-medium">{r.employee_name}</p>
                            <p className="text-muted-foreground font-mono text-xs">
                              {r.employee_code} · código {r.raw_code}
                            </p>
                          </>
                        ) : (
                          <p className="text-muted-foreground font-mono text-xs" title={r.raw}>
                            {r.raw_code || r.raw}
                          </p>
                        )}
                      </TD>
                      <TD className="whitespace-nowrap capitalize">{formatDay(r.timestamp)}</TD>
                      <TD className="font-mono tabular-nums">{formatTime(r.timestamp)}</TD>
                      <TD>{DIRECTION_LABEL[r.direction] ?? '—'}</TD>
                      <TD>
                        <Badge
                          variant={
                            r.status === 'valid'
                              ? 'success'
                              : r.status === 'error'
                                ? 'danger'
                                : 'neutral'
                          }
                        >
                          {r.status === 'valid'
                            ? 'Válida'
                            : r.status === 'error'
                              ? 'Error'
                              : 'Duplicada'}
                        </Badge>
                        {r.message && (
                          <p className="text-muted-foreground mt-1 text-xs">{r.message}</p>
                        )}
                      </TD>
                    </TR>
                  ))}
                </TBody>
              </Table>
              <Pager
                total={rows.data?.count ?? 0}
                page={page}
                onPage={setPage}
                noun={['fila', 'filas']}
              />
            </>
          )}
        </>
      )}
      {reverting && (
        <Dialog
          open
          onOpenChange={(o) => !o && setReverting(false)}
          title="Revertir importación"
          description={`Se anularán las ${b.punch_count} marcaciones vigentes de este lote (no se borran). Úsalo si el archivo era equivocado.`}
          footer={
            <>
              <Button variant="outline" onClick={() => setReverting(false)}>
                Cancelar
              </Button>
              <Button type="submit" form="revert-form" variant="danger" loading={revert.isPending}>
                Revertir
              </Button>
            </>
          }
        >
          <form
            id="revert-form"
            onSubmit={(e) => {
              e.preventDefault()
              reset()
              revert.mutate({ id, data: { reason } })
            }}
          >
            <FormField id="revert-reason" label="Motivo">
              <Input
                id="revert-reason"
                required
                value={reason}
                onChange={(e) => setReason(e.target.value)}
              />
            </FormField>
          </form>
        </Dialog>
      )}
    </div>
  )
}
