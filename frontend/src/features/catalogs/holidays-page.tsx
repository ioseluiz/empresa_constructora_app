import { useQueryClient } from '@tanstack/react-query'
import { CalendarPlus, Plus, Trash2 } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import {
  getOrgHolidaysListQueryKey,
  useOrgHolidaysCreate,
  useOrgHolidaysDestroy,
  useOrgHolidaysGenerateCreate,
  useOrgHolidaysList,
} from '@/api/generated/organizacion/organizacion'
import type { HolidayRequest } from '@/api/generated/model'
import { Alert } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Dialog } from '@/components/ui/dialog'
import { FormField } from '@/components/ui/form-field'
import { Input } from '@/components/ui/input'
import { EmptyState, LoadingBlock, PageHeader } from '@/components/ui/page'
import { Select } from '@/components/ui/select'
import { Table, TBody, TD, TH, THead, TR } from '@/components/ui/table'
import { formatDate } from '@/lib/format'
import { useFormErrors } from '@/lib/use-form-errors'

const KINDS: Record<string, string> = {
  national: 'Fiesta nacional',
  mourning: 'Duelo nacional',
  decreed: 'Decretado',
  company: 'De la empresa',
}

function weekday(value: string) {
  const [y, m, d] = value.split('-').map(Number)
  return new Intl.DateTimeFormat('es-PA', { weekday: 'long' }).format(new Date(y, m - 1, d))
}

function AddHolidayDialog({ year, onClose }: { year: number; onClose: () => void }) {
  const queryClient = useQueryClient()
  const [form, setForm] = useState({ date: `${year}-01-01`, name: '', kind: 'decreed' })
  const { errors, error, reset, handle } = useFormErrors()
  const create = useOrgHolidaysCreate({
    mutation: {
      onSuccess: () => {
        void queryClient.invalidateQueries({ queryKey: getOrgHolidaysListQueryKey() })
        onClose()
      },
      onError: handle,
    },
  })
  const submit = (e: FormEvent) => {
    e.preventDefault()
    reset()
    create.mutate({ data: { ...form, kind: form.kind as HolidayRequest['kind'] } })
  }
  return (
    <Dialog
      open
      onOpenChange={(o) => !o && onClose()}
      title="Agregar día feriado"
      description="Para días decretados por el Ejecutivo o descansos propios de la empresa."
      footer={
        <Button type="submit" form="holiday-form" loading={create.isPending}>
          Guardar
        </Button>
      }
    >
      <form id="holiday-form" onSubmit={submit} className="space-y-4">
        {error && <Alert>{error}</Alert>}
        <FormField id="h-date" label="Fecha" error={errors.date}>
          <Input
            id="h-date"
            type="date"
            required
            value={form.date}
            onChange={(e) => setForm({ ...form, date: e.target.value })}
          />
        </FormField>
        <FormField id="h-name" label="Nombre" error={errors.name}>
          <Input
            id="h-name"
            required
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
          />
        </FormField>
        <FormField id="h-kind" label="Tipo">
          <Select
            id="h-kind"
            className="w-full"
            value={form.kind}
            onChange={(e) => setForm({ ...form, kind: e.target.value })}
          >
            {Object.entries(KINDS).map(([v, l]) => (
              <option key={v} value={v}>
                {l}
              </option>
            ))}
          </Select>
        </FormField>
      </form>
    </Dialog>
  )
}

export function HolidaysPage() {
  const queryClient = useQueryClient()
  const [current] = useState(() => new Date().getFullYear())
  const [year, setYear] = useState(current)
  const [adding, setAdding] = useState(false)
  const holidays = useOrgHolidaysList({ year })
  const refresh = () =>
    void queryClient.invalidateQueries({ queryKey: getOrgHolidaysListQueryKey() })
  const generate = useOrgHolidaysGenerateCreate({ mutation: { onSuccess: refresh } })
  const destroy = useOrgHolidaysDestroy({ mutation: { onSuccess: refresh } })
  const rows = holidays.data ?? []

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <PageHeader
        title="Feriados"
        description="Días de fiesta y duelo nacional. El trabajo en estos días lleva recargo."
        actions={
          <>
            <Button variant="outline" onClick={() => setAdding(true)}>
              <Plus className="size-4" /> Agregar día
            </Button>
            <Button
              onClick={() => generate.mutate({ data: { year } })}
              loading={generate.isPending}
            >
              <CalendarPlus className="size-4" /> Cargar feriados {year}
            </Button>
          </>
        }
      />
      <div className="flex items-center gap-3">
        <Select value={year} onChange={(e) => setYear(Number(e.target.value))} aria-label="Año">
          {[current - 1, current, current + 1, current + 2].map((y) => (
            <option key={y} value={y}>
              {y}
            </option>
          ))}
        </Select>
        <p className="text-muted-foreground text-xs">
          Las fechas generadas siguen la ley vigente; verifica traslados o días decretados cada año.
        </p>
      </div>
      {holidays.isPending ? (
        <LoadingBlock />
      ) : rows.length === 0 ? (
        <EmptyState
          icon={CalendarPlus}
          title={`Sin feriados para ${year}`}
          description={`Usa "Cargar feriados ${year}" para generar los feriados nacionales.`}
        />
      ) : (
        <Table>
          <THead>
            <tr>
              <TH>Fecha</TH>
              <TH>Día</TH>
              <TH>Nombre</TH>
              <TH>Tipo</TH>
              <TH className="w-12" />
            </tr>
          </THead>
          <TBody>
            {rows.map((h) => (
              <TR key={h.id}>
                <TD className="whitespace-nowrap">{formatDate(h.date)}</TD>
                <TD className="text-muted-foreground capitalize">{weekday(h.date)}</TD>
                <TD>{h.name}</TD>
                <TD>
                  <Badge variant={h.kind === 'mourning' ? 'danger' : 'neutral'}>
                    {h.kind_display}
                  </Badge>
                </TD>
                <TD>
                  <Button
                    variant="ghost"
                    size="icon"
                    aria-label={`Eliminar ${h.name}`}
                    onClick={() => destroy.mutate({ id: h.id })}
                  >
                    <Trash2 className="size-4" />
                  </Button>
                </TD>
              </TR>
            ))}
          </TBody>
        </Table>
      )}
      {adding && <AddHolidayDialog year={year} onClose={() => setAdding(false)} />}
    </div>
  )
}
