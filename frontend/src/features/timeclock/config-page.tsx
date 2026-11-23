import { useQueryClient } from '@tanstack/react-query'
import { Plus, Trash2 } from 'lucide-react'
import { useState, type FormEvent, type ReactNode } from 'react'
import type { ClockCode, Device, ImportTemplate } from '@/api/generated/model'
import {
  getTimeclockClockCodesListQueryKey,
  getTimeclockDevicesListQueryKey,
  getTimeclockTemplatesListQueryKey,
  useTimeclockClockCodesCreate,
  useTimeclockClockCodesDestroy,
  useTimeclockClockCodesList,
  useTimeclockDevicesCreate,
  useTimeclockDevicesList,
  useTimeclockDevicesPartialUpdate,
  useTimeclockTemplatesCreate,
  useTimeclockTemplatesList,
  useTimeclockTemplatesPartialUpdate,
} from '@/api/generated/marcaciones/marcaciones'
import { useHrEmployeesList } from '@/api/generated/personal/personal'
import { useProjectsList } from '@/api/generated/proyectos/proyectos'
import { Alert } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Checkbox, Switch } from '@/components/ui/checkbox'
import { Dialog } from '@/components/ui/dialog'
import { FormField } from '@/components/ui/form-field'
import { Input } from '@/components/ui/input'
import { LoadingBlock, PageHeader } from '@/components/ui/page'
import { Select } from '@/components/ui/select'
import { Table, TBody, TD, TH, THead, TR } from '@/components/ui/table'
import { useAccess } from '@/features/access/use-access'
import { useFormErrors } from '@/lib/use-form-errors'
import { TimeclockTabs } from './timeclock-tabs'

function Section({
  title,
  description,
  action,
  children,
}: {
  title: string
  description: string
  action?: ReactNode
  children: ReactNode
}) {
  return (
    <section className="space-y-3">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold">{title}</h2>
          <p className="text-muted-foreground text-sm">{description}</p>
        </div>
        {action}
      </div>
      {children}
    </section>
  )
}

function DialogFooter({
  form,
  loading,
  onClose,
}: {
  form: string
  loading: boolean
  onClose: () => void
}) {
  return (
    <>
      <Button variant="outline" onClick={onClose}>
        Cancelar
      </Button>
      <Button type="submit" form={form} loading={loading}>
        Guardar
      </Button>
    </>
  )
}

function DeviceDialog({ device, onClose }: { device?: Device; onClose: () => void }) {
  const queryClient = useQueryClient()
  const projects = useProjectsList({ ordering: 'code' })
  const [form, setForm] = useState({
    name: device?.name ?? '',
    brand: device?.brand ?? 'zkteco',
    model: device?.model ?? '',
    serial_number: device?.serial_number ?? '',
    project: device?.project ?? '',
    location: device?.location ?? '',
    is_active: device?.is_active ?? true,
  })
  const { errors, error, reset, handle } = useFormErrors()
  const onSuccess = () => {
    void queryClient.invalidateQueries({ queryKey: getTimeclockDevicesListQueryKey() })
    onClose()
  }
  const create = useTimeclockDevicesCreate({ mutation: { onSuccess, onError: handle } })
  const update = useTimeclockDevicesPartialUpdate({ mutation: { onSuccess, onError: handle } })
  const submit = (e: FormEvent) => {
    e.preventDefault()
    reset()
    const data = { ...form, brand: form.brand as Device['brand'], project: form.project || null }
    if (device) update.mutate({ id: device.id, data })
    else create.mutate({ data })
  }
  const set =
    (key: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
      setForm({ ...form, [key]: e.target.value })
  return (
    <Dialog
      open
      onOpenChange={(o) => !o && onClose()}
      title={device ? `Editar ${device.name}` : 'Nuevo reloj'}
      footer={
        <DialogFooter
          form="device-form"
          loading={create.isPending || update.isPending}
          onClose={onClose}
        />
      }
    >
      <form id="device-form" onSubmit={submit} className="space-y-4">
        {error && <Alert>{error}</Alert>}
        <FormField id="dev-name" label="Nombre" error={errors.name}>
          <Input
            id="dev-name"
            required
            placeholder="Reloj entrada principal"
            value={form.name}
            onChange={set('name')}
          />
        </FormField>
        <div className="grid gap-4 sm:grid-cols-2">
          <FormField id="dev-brand" label="Marca" error={errors.brand}>
            <Select id="dev-brand" className="w-full" value={form.brand} onChange={set('brand')}>
              <option value="zkteco">ZKTeco</option>
              <option value="other">Otro</option>
            </Select>
          </FormField>
          <FormField id="dev-model" label="Modelo" error={errors.model}>
            <Input id="dev-model" value={form.model} onChange={set('model')} />
          </FormField>
          <FormField id="dev-serial" label="Número de serie" error={errors.serial_number}>
            <Input id="dev-serial" value={form.serial_number} onChange={set('serial_number')} />
          </FormField>
          <FormField id="dev-project" label="Proyecto" error={errors.project}>
            <Select
              id="dev-project"
              className="w-full"
              value={form.project}
              onChange={set('project')}
            >
              <option value="">Oficina central</option>
              {projects.data?.results.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.code} · {p.name}
                </option>
              ))}
            </Select>
          </FormField>
        </div>
        <FormField id="dev-location" label="Ubicación" error={errors.location}>
          <Input id="dev-location" value={form.location} onChange={set('location')} />
        </FormField>
        <label className="flex items-center gap-2 text-sm">
          <Switch
            checked={form.is_active}
            onCheckedChange={(v) => setForm({ ...form, is_active: v })}
          />{' '}
          Activo
        </label>
      </form>
    </Dialog>
  )
}

function ClockCodeDialog({ devices, onClose }: { devices: Device[]; onClose: () => void }) {
  const queryClient = useQueryClient()
  const [search, setSearch] = useState('')
  const employees = useHrEmployeesList({
    status: 'active',
    search: search || undefined,
    ordering: 'last_name',
  })
  const [form, setForm] = useState({ employee: '', device: '', code: '' })
  const { errors, error, reset, handle } = useFormErrors()
  const create = useTimeclockClockCodesCreate({
    mutation: {
      onSuccess: () => {
        void queryClient.invalidateQueries({ queryKey: getTimeclockClockCodesListQueryKey() })
        onClose()
      },
      onError: handle,
    },
  })
  return (
    <Dialog
      open
      onOpenChange={(o) => !o && onClose()}
      title="Asociar código de reloj"
      description="El número con el que el empleado está registrado en el reloj (PIN o ID de usuario)."
      footer={<DialogFooter form="code-form" loading={create.isPending} onClose={onClose} />}
    >
      <form
        id="code-form"
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault()
          reset()
          create.mutate({ data: { ...form, device: form.device || null } })
        }}
      >
        {error && <Alert>{error}</Alert>}
        <FormField id="code-employee" label="Empleado" error={errors.employee}>
          <Input
            type="search"
            placeholder="Buscar por nombre o cédula…"
            aria-label="Buscar empleado"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <Select
            id="code-employee"
            className="mt-2 w-full"
            required
            value={form.employee}
            onChange={(e) => setForm({ ...form, employee: e.target.value })}
          >
            <option value="">Selecciona…</option>
            {employees.data?.results.map((emp) => (
              <option key={emp.id} value={emp.id}>
                {emp.full_name} · {emp.code}
              </option>
            ))}
          </Select>
        </FormField>
        <div className="grid gap-4 sm:grid-cols-2">
          <FormField id="code-code" label="Código en el reloj" error={errors.code}>
            <Input
              id="code-code"
              required
              value={form.code}
              onChange={(e) => setForm({ ...form, code: e.target.value })}
            />
          </FormField>
          <FormField id="code-device" label="Reloj" error={errors.device}>
            <Select
              id="code-device"
              className="w-full"
              value={form.device}
              onChange={(e) => setForm({ ...form, device: e.target.value })}
            >
              <option value="">Todos los relojes</option>
              {devices.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name}
                </option>
              ))}
            </Select>
          </FormField>
        </div>
      </form>
    </Dialog>
  )
}

const TEMPLATE_FIELDS: [keyof ImportTemplate & string, string, string?][] = [
  ['employee_column', 'Columna del empleado', 'Nombre del encabezado o número (1 = primera)'],
  ['datetime_column', 'Columna de fecha y hora (juntas)'],
  ['date_column', 'Columna de fecha'],
  ['time_column', 'Columna de hora'],
  ['date_format', 'Formato de fecha', '%d/%m/%Y, %Y-%m-%d…'],
  ['time_format', 'Formato de hora', '%H:%M, %I:%M %p…'],
  ['direction_column', 'Columna de tipo (opcional)'],
  ['device_column', 'Columna del reloj (opcional)', 'Número de serie o nombre'],
  ['in_values', 'Valores que significan entrada'],
  ['out_values', 'Valores que significan salida'],
]

function TemplateDialog({ template, onClose }: { template?: ImportTemplate; onClose: () => void }) {
  const queryClient = useQueryClient()
  const [form, setForm] = useState<Record<string, string | boolean>>(() => ({
    name: template?.name ?? '',
    has_header: template?.has_header ?? true,
    delimiter: template?.delimiter ?? '',
    employee_key: template?.employee_key ?? 'clock_code',
    employee_column: template?.employee_column ?? '',
    datetime_column: template?.datetime_column ?? '',
    date_column: template?.date_column ?? '',
    time_column: template?.time_column ?? '',
    date_format: template?.date_format ?? '%d/%m/%Y',
    time_format: template?.time_format ?? '%H:%M',
    direction_column: template?.direction_column ?? '',
    device_column: template?.device_column ?? '',
    in_values: template?.in_values ?? 'E,ENTRADA,IN,I,0',
    out_values: template?.out_values ?? 'S,SALIDA,OUT,O,1',
  }))
  const { errors, error, reset, handle } = useFormErrors()
  const onSuccess = () => {
    void queryClient.invalidateQueries({ queryKey: getTimeclockTemplatesListQueryKey() })
    onClose()
  }
  const create = useTimeclockTemplatesCreate({ mutation: { onSuccess, onError: handle } })
  const update = useTimeclockTemplatesPartialUpdate({ mutation: { onSuccess, onError: handle } })
  const submit = (e: FormEvent) => {
    e.preventDefault()
    reset()
    const data = form as unknown as ImportTemplate
    if (template) update.mutate({ id: template.id, data })
    else create.mutate({ data })
  }
  return (
    <Dialog
      open
      size="lg"
      onOpenChange={(o) => !o && onClose()}
      title={template ? `Editar ${template.name}` : 'Nueva plantilla de importación'}
      description="Indica en qué columnas del Excel/CSV vienen el empleado, la fecha y la hora."
      footer={
        <DialogFooter
          form="template-form"
          loading={create.isPending || update.isPending}
          onClose={onClose}
        />
      }
    >
      <form
        id="template-form"
        onSubmit={submit}
        className="max-h-[65vh] space-y-4 overflow-y-auto pr-1"
      >
        {error && <Alert>{error}</Alert>}
        <div className="grid gap-4 sm:grid-cols-2">
          <FormField id="tpl-name" label="Nombre" error={errors.name as string}>
            <Input
              id="tpl-name"
              required
              value={form.name as string}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
            />
          </FormField>
          <FormField id="tpl-key" label="Identifica al empleado por" error={errors.employee_key}>
            <Select
              id="tpl-key"
              className="w-full"
              value={form.employee_key as string}
              onChange={(e) => setForm({ ...form, employee_key: e.target.value })}
            >
              <option value="clock_code">Código de reloj</option>
              <option value="employee_code">Número de empleado</option>
              <option value="id_number">Cédula / pasaporte</option>
            </Select>
          </FormField>
          {TEMPLATE_FIELDS.map(([key, label, hint]) => (
            <FormField key={key} id={`tpl-${key}`} label={label} error={errors[key]}>
              <Input
                id={`tpl-${key}`}
                placeholder={hint}
                required={key === 'employee_column'}
                value={form[key] as string}
                onChange={(e) => setForm({ ...form, [key]: e.target.value })}
              />
            </FormField>
          ))}
          <FormField id="tpl-delimiter" label="Separador CSV" error={errors.delimiter}>
            <Input
              id="tpl-delimiter"
              maxLength={1}
              placeholder="Automático"
              value={form.delimiter as string}
              onChange={(e) => setForm({ ...form, delimiter: e.target.value })}
            />
          </FormField>
          <label className="flex items-center gap-2 self-end pb-2 text-sm">
            <Checkbox
              checked={form.has_header as boolean}
              onChange={(e) => setForm({ ...form, has_header: e.target.checked })}
            />
            La primera fila es el encabezado
          </label>
        </div>
      </form>
    </Dialog>
  )
}

export function TimeclockConfigPage() {
  const queryClient = useQueryClient()
  const { can } = useAccess()
  const canEdit = can('timeclock.import')
  const devices = useTimeclockDevicesList()
  const codes = useTimeclockClockCodesList()
  const templates = useTimeclockTemplatesList()
  const [modal, setModal] = useState<
    | { kind: 'device'; device?: Device }
    | { kind: 'code' }
    | { kind: 'template'; template?: ImportTemplate }
    | null
  >(null)
  const [deleting, setDeleting] = useState<ClockCode | null>(null)
  const destroy = useTimeclockClockCodesDestroy({
    mutation: {
      onSuccess: () => {
        void queryClient.invalidateQueries({ queryKey: getTimeclockClockCodesListQueryKey() })
        setDeleting(null)
      },
    },
  })
  const addButton = (label: string, onClick: () => void) =>
    canEdit && (
      <Button variant="outline" onClick={onClick}>
        <Plus className="size-4" /> {label}
      </Button>
    )

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <PageHeader
        title="Marcaciones"
        description="Relojes, códigos de los empleados en cada reloj y plantillas para importar Excel/CSV."
      />
      <TimeclockTabs />

      <Section
        title="Relojes"
        description="Cada reloj pertenece a un proyecto (o a la oficina central): sus marcaciones se cargan a ese proyecto."
        action={addButton('Nuevo reloj', () => setModal({ kind: 'device' }))}
      >
        {devices.isPending ? (
          <LoadingBlock />
        ) : (
          <Table>
            <THead>
              <tr>
                <TH>Reloj</TH>
                <TH>Serie</TH>
                <TH>Proyecto</TH>
                <TH>Estado</TH>
              </tr>
            </THead>
            <TBody>
              {devices.data?.length === 0 && (
                <TR>
                  <TD colSpan={4} className="text-muted-foreground">
                    Aún no hay relojes registrados.
                  </TD>
                </TR>
              )}
              {devices.data?.map((d) => (
                <TR
                  key={d.id}
                  className={canEdit ? 'cursor-pointer' : undefined}
                  onClick={() => canEdit && setModal({ kind: 'device', device: d })}
                >
                  <TD>
                    <p className="font-medium">{d.name}</p>
                    <p className="text-muted-foreground text-xs">
                      {d.brand_display}
                      {d.model && ` ${d.model}`}
                      {d.location && ` · ${d.location}`}
                    </p>
                  </TD>
                  <TD className="font-mono text-xs">{d.serial_number || '—'}</TD>
                  <TD>{d.project_code ?? 'Oficina central'}</TD>
                  <TD>
                    <Badge variant={d.is_active ? 'success' : 'neutral'}>
                      {d.is_active ? 'Activo' : 'Inactivo'}
                    </Badge>
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
        )}
      </Section>

      <Section
        title="Códigos de reloj"
        description="Relaciona el código de cada empleado en el reloj con su expediente. Sin reloj = vale para todos."
        action={addButton('Asociar código', () => setModal({ kind: 'code' }))}
      >
        {codes.isPending ? (
          <LoadingBlock />
        ) : (
          <Table>
            <THead>
              <tr>
                <TH>Código</TH>
                <TH>Empleado</TH>
                <TH>Reloj</TH>
                {canEdit && <TH className="w-12" />}
              </tr>
            </THead>
            <TBody>
              {codes.data?.length === 0 && (
                <TR>
                  <TD colSpan={4} className="text-muted-foreground">
                    Sin códigos asociados: las filas del archivo saldrán como "sin empleado".
                  </TD>
                </TR>
              )}
              {codes.data?.map((c) => (
                <TR key={c.id}>
                  <TD className="font-mono">{c.code}</TD>
                  <TD>
                    {c.employee_name}{' '}
                    <span className="text-muted-foreground font-mono text-xs">
                      {c.employee_code}
                    </span>
                  </TD>
                  <TD className="text-muted-foreground">{c.device_name ?? 'Todos'}</TD>
                  {canEdit && (
                    <TD>
                      <Button
                        size="icon"
                        variant="ghost"
                        aria-label="Quitar código"
                        onClick={() => setDeleting(c)}
                      >
                        <Trash2 className="size-4" />
                      </Button>
                    </TD>
                  )}
                </TR>
              ))}
            </TBody>
          </Table>
        )}
      </Section>

      <Section
        title="Plantillas de importación"
        description="Para Excel o CSV exportados de otros sistemas de asistencia."
        action={addButton('Nueva plantilla', () => setModal({ kind: 'template' }))}
      >
        <Card>
          <CardContent className="divide-y p-0">
            {templates.data?.length === 0 && (
              <p className="text-muted-foreground p-4 text-sm">Aún no hay plantillas.</p>
            )}
            {templates.data?.map((t) => (
              <button
                key={t.id}
                type="button"
                disabled={!canEdit}
                onClick={() => setModal({ kind: 'template', template: t })}
                className="hover:bg-muted/40 flex w-full items-center justify-between px-4 py-3 text-left text-sm"
              >
                <span className="font-medium">{t.name}</span>
                <span className="text-muted-foreground text-xs">
                  Empleado: {t.employee_column} ·{' '}
                  {t.datetime_column
                    ? `Fecha y hora: ${t.datetime_column}`
                    : `Fecha: ${t.date_column} · Hora: ${t.time_column}`}
                </span>
              </button>
            ))}
          </CardContent>
        </Card>
      </Section>

      {modal?.kind === 'device' && (
        <DeviceDialog device={modal.device} onClose={() => setModal(null)} />
      )}
      {modal?.kind === 'code' && (
        <ClockCodeDialog devices={devices.data ?? []} onClose={() => setModal(null)} />
      )}
      {modal?.kind === 'template' && (
        <TemplateDialog template={modal.template} onClose={() => setModal(null)} />
      )}
      {deleting && (
        <Dialog
          open
          onOpenChange={(o) => !o && setDeleting(null)}
          title="Quitar código de reloj"
          description={`El código ${deleting.code} dejará de asociarse a ${deleting.employee_name}. Las marcaciones ya importadas no cambian.`}
          footer={
            <>
              <Button variant="outline" onClick={() => setDeleting(null)}>
                Cancelar
              </Button>
              <Button
                variant="danger"
                loading={destroy.isPending}
                onClick={() => destroy.mutate({ id: deleting.id })}
              >
                Quitar
              </Button>
            </>
          }
        />
      )}
    </div>
  )
}
