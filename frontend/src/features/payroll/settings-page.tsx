import { useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import type { PayrollSettings } from '@/api/generated/model'
import {
  getPayrollSettingsRetrieveQueryKey,
  usePayrollSettingsPartialUpdate,
  usePayrollSettingsRetrieve,
} from '@/api/generated/planilla/planilla'
import { Alert } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Switch } from '@/components/ui/checkbox'
import { FormField } from '@/components/ui/form-field'
import { Input } from '@/components/ui/input'
import { LoadingBlock, PageHeader } from '@/components/ui/page'
import { useAccess } from '@/features/access/use-access'
import { useFormErrors } from '@/lib/use-form-errors'
import { PayrollTabs } from './payroll-tabs'

const toPercent = (v?: string) => (v ? String(Number((Number(v) * 100).toFixed(4))) : '0')
const toFraction = (v: string) => (Number(v || 0) / 100).toFixed(6)

function SettingsForm({ settings, canEdit }: { settings: PayrollSettings; canEdit: boolean }) {
  const queryClient = useQueryClient()
  const [form, setForm] = useState({
    risk: toPercent(settings.occupational_risk_rate),
    union: toPercent(settings.union_dues_rate),
    deduct: settings.deduct_unworked_time ?? true,
  })
  const [saved, setSaved] = useState(false)
  const { errors, error, reset, handle } = useFormErrors()
  const update = usePayrollSettingsPartialUpdate({
    mutation: {
      onSuccess: () => {
        void queryClient.invalidateQueries({ queryKey: getPayrollSettingsRetrieveQueryKey() })
        setSaved(true)
      },
      onError: handle,
    },
  })
  const submit = (e: FormEvent) => {
    e.preventDefault()
    reset()
    setSaved(false)
    update.mutate({
      data: {
        occupational_risk_rate: toFraction(form.risk),
        union_dues_rate: toFraction(form.union),
        deduct_unworked_time: form.deduct,
      },
    })
  }
  return (
    <Card>
      <CardContent className="pt-5">
        <form onSubmit={submit} className="max-w-xl space-y-5">
          {error && <Alert>{error}</Alert>}
          {!canEdit && (
            <Alert>Solo lectura: necesitas el permiso de configuración de planilla.</Alert>
          )}
          <FormField
            id="set-risk"
            label="Tasa de riesgos profesionales (%)"
            error={errors.occupational_risk_rate}
            hint={
              <span className="text-muted-foreground text-xs">
                Asignada por la CSS a la empresa
              </span>
            }
          >
            <Input
              id="set-risk"
              type="number"
              step="0.0001"
              min="0"
              max="100"
              disabled={!canEdit}
              value={form.risk}
              onChange={(e) => setForm({ ...form, risk: e.target.value })}
            />
          </FormField>
          <FormField
            id="set-union"
            label="Cuota sindical (% del salario bruto)"
            error={errors.union_dues_rate}
            hint={<span className="text-muted-foreground text-xs">Para empleados afiliados</span>}
          >
            <Input
              id="set-union"
              type="number"
              step="0.01"
              min="0"
              max="20"
              disabled={!canEdit}
              value={form.union}
              onChange={(e) => setForm({ ...form, union: e.target.value })}
            />
          </FormField>
          <label className="flex items-start gap-3 text-sm">
            <Switch
              checked={form.deduct}
              disabled={!canEdit}
              onCheckedChange={(v) => setForm({ ...form, deduct: v })}
            />
            <span>
              Descontar a los asalariados el tiempo no laborado
              <span className="text-muted-foreground block text-xs">
                Ausencias, tardanzas y salidas anticipadas de jornadas aprobadas, al valor hora.
              </span>
            </span>
          </label>
          {canEdit && (
            <div className="flex items-center gap-3">
              <Button type="submit" loading={update.isPending}>
                Guardar
              </Button>
              {saved && <span className="text-success text-sm">Guardado.</span>}
            </div>
          )}
        </form>
      </CardContent>
    </Card>
  )
}

export function PayrollSettingsPage() {
  const { can } = useAccess()
  const settings = usePayrollSettingsRetrieve()
  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <PageHeader
        title="Planilla"
        description="Valores propios de la empresa que usa el cálculo de la planilla."
      />
      <PayrollTabs />
      {settings.isPending || !settings.data ? (
        <LoadingBlock />
      ) : (
        <SettingsForm settings={settings.data} canEdit={can('payroll.config')} />
      )}
    </div>
  )
}
