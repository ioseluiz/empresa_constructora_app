import { useQueryClient } from '@tanstack/react-query'
import { FileUp, Upload } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import type { ImportBatchSourceEnum } from '@/api/generated/model'
import {
  getTimeclockBatchesListQueryKey,
  useTimeclockBatchesCreate,
  useTimeclockBatchesList,
  useTimeclockDevicesList,
  useTimeclockTemplatesList,
} from '@/api/generated/marcaciones/marcaciones'
import { useProjectsList } from '@/api/generated/proyectos/proyectos'
import { Alert } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Dialog } from '@/components/ui/dialog'
import { FormField } from '@/components/ui/form-field'
import { Input } from '@/components/ui/input'
import { EmptyState, LoadingBlock, PageHeader } from '@/components/ui/page'
import { Pager } from '@/components/ui/pager'
import { Select } from '@/components/ui/select'
import { Table, TBody, TD, TH, THead, TR } from '@/components/ui/table'
import { formatDateTime, formatDay } from '@/lib/format'
import { useFormErrors } from '@/lib/use-form-errors'
import { cn } from '@/lib/utils'
import { BATCH_STATUS } from './constants'
import { TimeclockTabs } from './timeclock-tabs'

const MAX_SIZE = 10 * 1024 * 1024

function ImportDialog({ onClose }: { onClose: () => void }) {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const devices = useTimeclockDevicesList({ is_active: true })
  const templates = useTimeclockTemplatesList()
  const projects = useProjectsList({ ordering: 'code', status: 'active' })
  const [source, setSource] = useState<ImportBatchSourceEnum>('zkteco')
  const [device, setDevice] = useState('')
  const [template, setTemplate] = useState('')
  const [project, setProject] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const { errors, error, setError, reset, handle } = useFormErrors()
  const create = useTimeclockBatchesCreate({
    mutation: {
      onSuccess: (batch) => {
        void queryClient.invalidateQueries({ queryKey: getTimeclockBatchesListQueryKey() })
        void navigate(`/marcaciones/importaciones/${batch.id}`)
      },
      onError: handle,
    },
  })
  const submit = (e: FormEvent) => {
    e.preventDefault()
    reset()
    if (!file) return setError('Selecciona el archivo.')
    if (file.size > MAX_SIZE) return setError('El archivo supera el máximo de 10 MB.')
    create.mutate({
      data: {
        source,
        file,
        device: device || null,
        template: source === 'template' ? template || null : null,
        project: project || null,
      },
    })
  }
  const noDevices = devices.data?.length === 0
  const noTemplates = templates.data?.length === 0

  return (
    <Dialog
      open
      onOpenChange={(o) => !o && onClose()}
      title="Importar marcaciones"
      description="El archivo se analiza en segundo plano. Antes de guardar verás una vista previa con errores y duplicados."
      footer={
        <>
          <Button variant="outline" onClick={onClose}>
            Cancelar
          </Button>
          <Button type="submit" form="import-form" loading={create.isPending}>
            Analizar archivo
          </Button>
        </>
      }
    >
      <form id="import-form" onSubmit={submit} className="space-y-4">
        {error && <Alert>{error}</Alert>}
        <div className="grid grid-cols-2 gap-2" role="radiogroup" aria-label="Origen">
          {(
            [
              ['zkteco', 'Reloj ZKTeco', 'Archivo attlog (.dat / .txt)'],
              ['template', 'Excel / CSV', 'De otro sistema, con plantilla'],
            ] as const
          ).map(([value, title, hint]) => (
            <button
              key={value}
              type="button"
              role="radio"
              aria-checked={source === value}
              onClick={() => setSource(value)}
              className={cn(
                'rounded-md border p-3 text-left transition-colors',
                source === value ? 'border-primary bg-primary/5' : 'hover:bg-muted',
              )}
            >
              <p className="text-sm font-medium">{title}</p>
              <p className="text-muted-foreground text-xs">{hint}</p>
            </button>
          ))}
        </div>
        {source === 'template' && (
          <FormField id="imp-template" label="Plantilla de columnas" error={errors.template}>
            <Select
              id="imp-template"
              className="w-full"
              required
              value={template}
              onChange={(e) => setTemplate(e.target.value)}
            >
              <option value="">Selecciona…</option>
              {templates.data?.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name}
                </option>
              ))}
            </Select>
            {noTemplates && (
              <p className="text-muted-foreground text-xs">
                Crea una plantilla en{' '}
                <Link to="/marcaciones/configuracion" className="text-primary hover:underline">
                  Relojes y plantillas
                </Link>
                .
              </p>
            )}
          </FormField>
        )}
        <FormField
          id="imp-device"
          label={source === 'zkteco' ? 'Reloj' : 'Reloj (si el archivo no lo indica)'}
          error={errors.device}
        >
          <Select
            id="imp-device"
            className="w-full"
            required={source === 'zkteco'}
            value={device}
            onChange={(e) => setDevice(e.target.value)}
          >
            <option value="">{source === 'zkteco' ? 'Selecciona…' : 'Ninguno'}</option>
            {devices.data?.map((d) => (
              <option key={d.id} value={d.id}>
                {d.name}
                {d.project_code ? ` · ${d.project_code}` : ' · Oficina central'}
              </option>
            ))}
          </Select>
          {noDevices && (
            <p className="text-muted-foreground text-xs">
              Registra el reloj en{' '}
              <Link to="/marcaciones/configuracion" className="text-primary hover:underline">
                Relojes y plantillas
              </Link>
              .
            </p>
          )}
        </FormField>
        <FormField
          id="imp-project"
          label="Proyecto (si el reloj no tiene uno)"
          error={errors.project}
        >
          <Select
            id="imp-project"
            className="w-full"
            value={project}
            onChange={(e) => setProject(e.target.value)}
          >
            <option value="">Según el reloj</option>
            {projects.data?.results.map((p) => (
              <option key={p.id} value={p.id}>
                {p.code} · {p.name}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField id="imp-file" label="Archivo" error={errors.file}>
          <Input
            id="imp-file"
            type="file"
            required
            accept={source === 'zkteco' ? '.dat,.txt,.csv,.log' : '.csv,.txt,.xlsx,.xlsm'}
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          />
        </FormField>
      </form>
    </Dialog>
  )
}

export function ImportsPage() {
  const [page, setPage] = useState(1)
  const [importing, setImporting] = useState(false)
  const batches = useTimeclockBatchesList({ page })
  const rows = batches.data?.results ?? []

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <PageHeader
        title="Marcaciones"
        description="Importa los archivos de los relojes o de otros sistemas. Un lote confirmado puede revertirse si se importó por error."
        actions={
          <Button onClick={() => setImporting(true)}>
            <Upload className="size-4" /> Importar archivo
          </Button>
        }
      />
      <TimeclockTabs />
      {batches.isPending ? (
        <LoadingBlock />
      ) : rows.length === 0 ? (
        <EmptyState
          icon={FileUp}
          title="Aún no hay importaciones"
          description="Sube el archivo exportado del reloj para empezar."
        />
      ) : (
        <>
          <Table>
            <THead>
              <tr>
                <TH>Archivo</TH>
                <TH>Origen</TH>
                <TH>Período</TH>
                <TH className="text-right">Válidas</TH>
                <TH className="text-right">Errores</TH>
                <TH>Estado</TH>
                <TH>Subido</TH>
              </tr>
            </THead>
            <TBody>
              {rows.map((b) => {
                const st = BATCH_STATUS[b.status]
                return (
                  <TR key={b.id}>
                    <TD>
                      <Link
                        to={`/marcaciones/importaciones/${b.id}`}
                        className="text-primary font-medium hover:underline"
                      >
                        {b.original_name}
                      </Link>
                    </TD>
                    <TD className="text-muted-foreground">
                      {b.source === 'zkteco' ? b.device_name : b.template_name}
                    </TD>
                    <TD className="text-xs whitespace-nowrap">
                      {b.first_punch
                        ? `${formatDay(b.first_punch)} – ${formatDay(b.last_punch)}`
                        : '—'}
                    </TD>
                    <TD className="text-right tabular-nums">{b.valid_rows}</TD>
                    <TD
                      className={cn('text-right tabular-nums', b.error_rows > 0 && 'text-danger')}
                    >
                      {b.error_rows}
                    </TD>
                    <TD>
                      <Badge variant={st.variant}>{st.label}</Badge>
                    </TD>
                    <TD className="text-muted-foreground text-xs whitespace-nowrap">
                      {formatDateTime(b.created_at)}
                      <p>{b.created_by_email}</p>
                    </TD>
                  </TR>
                )
              })}
            </TBody>
          </Table>
          <Pager
            total={batches.data?.count ?? 0}
            page={page}
            onPage={setPage}
            noun={['importación', 'importaciones']}
          />
        </>
      )}
      {importing && <ImportDialog onClose={() => setImporting(false)} />}
    </div>
  )
}
