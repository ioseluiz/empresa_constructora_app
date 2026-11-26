import { useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import type { PatchedPayrollSettingsRequest, PayrollSettings } from '@/api/generated/model'
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
import { Select } from '@/components/ui/select'
import { LoadingBlock, PageHeader } from '@/components/ui/page'
import { useAccess } from '@/features/access/use-access'
import { BANKS } from '@/features/employees/constants'
import { Options } from '@/features/employees/employee-dialog'
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
    showEmployer: settings.payslip_show_employer ?? false,
    bank: (settings.company_bank as string) ?? '',
    accountType: (settings.company_account_type as string) ?? '',
    account: settings.company_account_number ?? '',
  })
  const [routes, setRoutes] = useState<Record<string, string>>(
    (settings.ach_routes as Record<string, string> | undefined) ?? {},
  )
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
        payslip_show_employer: form.showEmployer,
        company_bank: form.bank as PatchedPayrollSettingsRequest['company_bank'],
        company_account_type:
          form.accountType as PatchedPayrollSettingsRequest['company_account_type'],
        company_account_number: form.account,
        ach_routes: Object.fromEntries(Object.entries(routes).filter(([, v]) => v)),
      },
    })
  }
  return (
    <Card>
      <CardContent className="pt-5">
        <form onSubmit={submit} className="max-w-3xl space-y-5">
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
          <label className="flex items-start gap-3 text-sm">
            <Switch
              checked={form.showEmployer}
              disabled={!canEdit}
              onCheckedChange={(v) => setForm({ ...form, showEmployer: v })}
            />
            <span>
              Mostrar los aportes del empleador en el comprobante de pago
              <span className="text-muted-foreground block text-xs">
                Seguro Social y Educativo patronal, riesgos profesionales (informativo).
              </span>
            </span>
          </label>

          <fieldset className="space-y-3 border-t pt-4">
            <legend className="text-sm font-semibold">Pagos por ACH</legend>
            <div className="grid gap-4 sm:grid-cols-3">
              <FormField id="set-bank" label="Banco de la empresa" error={errors.company_bank}>
                <Select
                  id="set-bank"
                  className="w-full"
                  disabled={!canEdit}
                  value={form.bank}
                  onChange={(e) => setForm({ ...form, bank: e.target.value })}
                >
                  <Options empty="—" items={BANKS} />
                </Select>
              </FormField>
              <FormField
                id="set-acct-type"
                label="Tipo de cuenta"
                error={errors.company_account_type}
              >
                <Select
                  id="set-acct-type"
                  className="w-full"
                  disabled={!canEdit}
                  value={form.accountType}
                  onChange={(e) => setForm({ ...form, accountType: e.target.value })}
                >
                  <Options
                    empty="—"
                    items={[
                      ['checking', 'Corriente'],
                      ['savings', 'Ahorros'],
                    ]}
                  />
                </Select>
              </FormField>
              <FormField
                id="set-account"
                label="Número de cuenta"
                error={errors.company_account_number}
              >
                <Input
                  id="set-account"
                  inputMode="numeric"
                  disabled={!canEdit}
                  value={form.account}
                  onChange={(e) => setForm({ ...form, account: e.target.value })}
                />
              </FormField>
            </div>
            <div className="space-y-2">
              <p className="text-sm font-medium">Códigos de ruta ACH</p>
              <p className="text-muted-foreground text-xs">
                Los proporciona el banco al habilitar el servicio ACH. Solo se necesitan los de los
                bancos de tus empleados.
              </p>
              {errors.ach_routes && <p className="text-danger text-xs">{errors.ach_routes}</p>}
              <div className="grid gap-x-4 gap-y-2 sm:grid-cols-2">
                {BANKS.filter(([code]) => code !== 'other').map(([code, name]) => (
                  <label key={code} className="flex items-center justify-between gap-3 text-sm">
                    <span className="truncate">{name}</span>
                    <Input
                      className="h-8 w-24"
                      inputMode="numeric"
                      aria-label={`Ruta ACH ${name}`}
                      disabled={!canEdit}
                      value={routes[code] ?? ''}
                      onChange={(e) =>
                        setRoutes({ ...routes, [code]: e.target.value.replace(/\D/g, '') })
                      }
                    />
                  </label>
                ))}
              </div>
            </div>
          </fieldset>

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
