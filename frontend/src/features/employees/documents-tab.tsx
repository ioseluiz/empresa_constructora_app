import { useQueryClient } from '@tanstack/react-query'
import { Download, FileText, Trash2, Upload } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { downloadFile } from '@/api/client'
import type { Employee, EmployeeDocument, EmployeeDocumentKindEnum } from '@/api/generated/model'
import {
  getHrDocumentsDownloadRetrieveUrl,
  getHrDocumentsListQueryKey,
  useHrDocumentsCreate,
  useHrDocumentsDestroy,
  useHrDocumentsList,
} from '@/api/generated/personal/personal'
import { Alert } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Dialog } from '@/components/ui/dialog'
import { FormField } from '@/components/ui/form-field'
import { Input } from '@/components/ui/input'
import { EmptyState, LoadingBlock } from '@/components/ui/page'
import { Select } from '@/components/ui/select'
import { Table, TBody, TD, TH, THead, TR } from '@/components/ui/table'
import { useAccess } from '@/features/access/use-access'
import { formatDate } from '@/lib/format'
import { useFormErrors } from '@/lib/use-form-errors'
import { DOCUMENT_KINDS, todayISO } from './constants'
import { Options } from './employee-dialog'

const MAX_SIZE = 10 * 1024 * 1024
const ACCEPT = 'application/pdf,image/jpeg,image/png'

function formatSize(bytes: number) {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function expiry(doc: EmployeeDocument, today: string) {
  if (!doc.expires_on) return null
  const soon = new Date(`${today}T00:00:00`)
  soon.setDate(soon.getDate() + 30)
  const limit = soon.toISOString().slice(0, 10)
  if (doc.expires_on < today) return { label: 'Vencido', variant: 'danger' as const }
  if (doc.expires_on <= limit) return { label: 'Vence pronto', variant: 'danger' as const }
  return null
}

function UploadDialog({ employee, onClose }: { employee: Employee; onClose: () => void }) {
  const queryClient = useQueryClient()
  const [kind, setKind] = useState('id_copy')
  const [title, setTitle] = useState('')
  const [expiresOn, setExpiresOn] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const { errors, error, setError, reset, handle } = useFormErrors()
  const create = useHrDocumentsCreate({
    mutation: {
      onSuccess: () => {
        void queryClient.invalidateQueries({ queryKey: getHrDocumentsListQueryKey() })
        onClose()
      },
      onError: handle,
    },
  })
  const submit = (e: FormEvent) => {
    e.preventDefault()
    reset()
    if (!file) return setError('Selecciona un archivo.')
    if (file.size > MAX_SIZE) return setError('El archivo supera el máximo de 10 MB.')
    create.mutate({
      data: {
        employee: employee.id,
        kind: kind as EmployeeDocumentKindEnum,
        title,
        file,
        expires_on: expiresOn || null,
      },
    })
  }
  return (
    <Dialog
      open
      onOpenChange={(o) => !o && onClose()}
      title="Subir documento"
      description="PDF, JPG o PNG de hasta 10 MB. Solo los usuarios con acceso al expediente pueden descargarlo."
      footer={
        <>
          <Button variant="outline" onClick={onClose}>
            Cancelar
          </Button>
          <Button type="submit" form="doc-form" loading={create.isPending}>
            Subir
          </Button>
        </>
      }
    >
      <form id="doc-form" onSubmit={submit} className="space-y-4">
        {error && <Alert>{error}</Alert>}
        <FormField id="doc-kind" label="Tipo" error={errors.kind}>
          <Select
            id="doc-kind"
            className="w-full"
            value={kind}
            onChange={(e) => setKind(e.target.value)}
          >
            <Options items={DOCUMENT_KINDS} />
          </Select>
        </FormField>
        <FormField id="doc-title" label="Descripción (opcional)" error={errors.title}>
          <Input id="doc-title" value={title} onChange={(e) => setTitle(e.target.value)} />
        </FormField>
        <FormField id="doc-expires" label="Vence (opcional)" error={errors.expires_on}>
          <Input
            id="doc-expires"
            type="date"
            value={expiresOn}
            onChange={(e) => setExpiresOn(e.target.value)}
          />
        </FormField>
        <FormField id="doc-file" label="Archivo" error={errors.file}>
          <Input
            id="doc-file"
            type="file"
            accept={ACCEPT}
            required
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          />
        </FormField>
      </form>
    </Dialog>
  )
}

export function DocumentsTab({ employee }: { employee: Employee }) {
  const queryClient = useQueryClient()
  const { can } = useAccess()
  const canManage = can('hr.employee.manage')
  const [uploading, setUploading] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState<EmployeeDocument | null>(null)
  const [downloadError, setDownloadError] = useState<string | null>(null)
  const documents = useHrDocumentsList({ employee: employee.id })
  const destroy = useHrDocumentsDestroy({
    mutation: {
      onSuccess: () => {
        void queryClient.invalidateQueries({ queryKey: getHrDocumentsListQueryKey() })
        setConfirmDelete(null)
      },
    },
  })
  const download = (doc: EmployeeDocument) => {
    setDownloadError(null)
    downloadFile(getHrDocumentsDownloadRetrieveUrl(doc.id), doc.original_name).catch(() =>
      setDownloadError('No se pudo descargar el documento.'),
    )
  }
  const today = todayISO()
  const rows = documents.data ?? []

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-4">
        <p className="text-muted-foreground text-sm">
          Copias de cédula, carné del seguro social, contratos firmados y otros soportes.
        </p>
        {canManage && (
          <Button onClick={() => setUploading(true)}>
            <Upload className="size-4" /> Subir documento
          </Button>
        )}
      </div>
      {downloadError && <Alert>{downloadError}</Alert>}
      {documents.isPending ? (
        <LoadingBlock />
      ) : rows.length === 0 ? (
        <EmptyState icon={FileText} title="Sin documentos" />
      ) : (
        <Table>
          <THead>
            <tr>
              <TH>Documento</TH>
              <TH>Archivo</TH>
              <TH>Vence</TH>
              <TH>Subido</TH>
              <TH className="w-24" />
            </tr>
          </THead>
          <TBody>
            {rows.map((d) => {
              const exp = expiry(d, today)
              return (
                <TR key={d.id}>
                  <TD>
                    <p className="font-medium">{d.kind_display}</p>
                    {d.title && <p className="text-muted-foreground text-xs">{d.title}</p>}
                  </TD>
                  <TD>
                    <p className="max-w-56 truncate" title={d.original_name}>
                      {d.original_name}
                    </p>
                    <p className="text-muted-foreground text-xs">{formatSize(d.size)}</p>
                  </TD>
                  <TD className="whitespace-nowrap">
                    {d.expires_on ? formatDate(d.expires_on) : '—'}
                    {exp && (
                      <Badge variant={exp.variant} className="ml-2">
                        {exp.label}
                      </Badge>
                    )}
                  </TD>
                  <TD className="text-muted-foreground text-xs whitespace-nowrap">
                    {formatDate(d.created_at.slice(0, 10))}
                    {d.uploaded_by && <p>{d.uploaded_by}</p>}
                  </TD>
                  <TD className="text-right whitespace-nowrap">
                    <Button
                      size="icon"
                      variant="ghost"
                      aria-label="Descargar"
                      onClick={() => download(d)}
                    >
                      <Download className="size-4" />
                    </Button>
                    {canManage && (
                      <Button
                        size="icon"
                        variant="ghost"
                        aria-label="Eliminar"
                        onClick={() => setConfirmDelete(d)}
                      >
                        <Trash2 className="size-4" />
                      </Button>
                    )}
                  </TD>
                </TR>
              )
            })}
          </TBody>
        </Table>
      )}
      {uploading && <UploadDialog employee={employee} onClose={() => setUploading(false)} />}
      {confirmDelete && (
        <Dialog
          open
          onOpenChange={(o) => !o && setConfirmDelete(null)}
          title="Eliminar documento"
          description={`Se eliminará "${confirmDelete.original_name}" de forma permanente. Quedará registro en la bitácora.`}
          footer={
            <>
              <Button variant="outline" onClick={() => setConfirmDelete(null)}>
                Cancelar
              </Button>
              <Button
                variant="danger"
                loading={destroy.isPending}
                onClick={() => destroy.mutate({ id: confirmDelete.id })}
              >
                Eliminar
              </Button>
            </>
          }
        />
      )}
    </div>
  )
}
