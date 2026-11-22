import { useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent, type ReactNode } from 'react'
import type { Employee, EmployeeRequest } from '@/api/generated/model'
import {
  getHrEmployeesListQueryKey,
  getHrEmployeesRetrieveQueryKey,
  useHrEmployeesCreate,
  useHrEmployeesPartialUpdate,
} from '@/api/generated/personal/personal'
import { Alert } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Dialog } from '@/components/ui/dialog'
import { FormField } from '@/components/ui/form-field'
import { Input } from '@/components/ui/input'
import { Select } from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { useAccess } from '@/features/access/use-access'
import { PROVINCES } from '@/features/projects/constants'
import { useFormErrors } from '@/lib/use-form-errors'
import { BANKS, CEDULA_PATTERN, MARITAL_STATUS } from './constants'

const FIELDS = [
  'code',
  'first_name',
  'middle_name',
  'last_name',
  'second_last_name',
  'id_type',
  'id_number',
  'css_number',
  'birth_date',
  'sex',
  'marital_status',
  'nationality',
  'email',
  'phone',
  'address',
  'province',
  'emergency_contact_name',
  'emergency_contact_phone',
  'payment_method',
  'bank',
  'account_type',
  'account_number',
  'hire_date',
  'notes',
] as const

type Field = (typeof FIELDS)[number]
type Form = Record<Field, string> & { is_union_member: boolean }

const BANK_FIELDS: Field[] = ['bank', 'account_type', 'account_number']

function toForm(e?: Employee): Form {
  const form = Object.fromEntries(
    FIELDS.map((f) => [f, (e?.[f as keyof Employee] as string | null | undefined) ?? '']),
  ) as unknown as Form
  form.id_type ||= 'cedula'
  form.nationality ||= 'Panameña'
  form.payment_method ||= 'ach'
  form.is_union_member = e?.is_union_member ?? false
  return form
}

export function Options({ items, empty }: { items: [string, string][]; empty?: string }) {
  return (
    <>
      {empty !== undefined && <option value="">{empty}</option>}
      {items.map(([v, label]) => (
        <option key={v} value={v}>
          {label}
        </option>
      ))}
    </>
  )
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <fieldset className="space-y-3">
      <legend className="text-muted-foreground mb-2 text-xs font-semibold tracking-wide uppercase">
        {title}
      </legend>
      <div className="grid gap-4 sm:grid-cols-2">{children}</div>
    </fieldset>
  )
}

export function EmployeeDialog({
  employee,
  onClose,
  onCreated,
}: {
  employee?: Employee
  onClose: () => void
  onCreated?: (e: Employee) => void
}) {
  const queryClient = useQueryClient()
  const { can } = useAccess()
  const canSeeBank = can('hr.salary.view')
  const [form, setForm] = useState<Form>(() => toForm(employee))
  const { errors, error, setError, reset, handle } = useFormErrors()
  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: getHrEmployeesListQueryKey() }).then(() => {
      if (employee)
        void queryClient.invalidateQueries({
          queryKey: getHrEmployeesRetrieveQueryKey(employee.id),
        })
    })
  const create = useHrEmployeesCreate({
    mutation: {
      onSuccess: (created) => {
        void invalidate()
        onCreated?.(created)
        onClose()
      },
      onError: handle,
    },
  })
  const update = useHrEmployeesPartialUpdate({
    mutation: {
      onSuccess: () => {
        void invalidate()
        onClose()
      },
      onError: handle,
    },
  })

  const submit = (e: FormEvent) => {
    e.preventDefault()
    reset()
    const idNumber = form.id_number.trim().toUpperCase()
    if (form.id_type === 'cedula' && !CEDULA_PATTERN.test(idNumber)) {
      setError('Revisa la cédula: formato 8-123-4567, 4PI-12-345 o E-8-1234.')
      return
    }
    const payload: Record<string, unknown> = { ...form, id_number: idNumber }
    payload.birth_date = form.birth_date || null
    if (!canSeeBank) BANK_FIELDS.forEach((f) => delete payload[f])
    if (form.payment_method !== 'ach' && canSeeBank) {
      payload.bank = ''
      payload.account_type = ''
      payload.account_number = ''
    }
    const data = payload as unknown as EmployeeRequest
    if (employee) update.mutate({ id: employee.id, data })
    else create.mutate({ data })
  }

  const bind = (key: Field) => ({
    id: `emp-${key}`,
    value: form[key],
    'aria-invalid': !!errors[key],
    onChange: (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) =>
      setForm({ ...form, [key]: e.target.value }),
  })
  const field = (key: Field, label: string, input: ReactNode) => (
    <FormField id={`emp-${key}`} label={label} error={errors[key]}>
      {input}
    </FormField>
  )

  return (
    <Dialog
      open
      size="lg"
      onOpenChange={(o) => !o && onClose()}
      title={employee ? `Editar ${employee.full_name}` : 'Nuevo empleado'}
      description={
        employee
          ? 'Datos del expediente. Los contratos y salarios se gestionan en su pestaña.'
          : 'Después de crearlo podrás registrar su contrato, salario y asignarlo a proyectos.'
      }
      footer={
        <>
          <Button variant="outline" onClick={onClose}>
            Cancelar
          </Button>
          <Button type="submit" form="employee-form" loading={create.isPending || update.isPending}>
            {employee ? 'Guardar' : 'Crear empleado'}
          </Button>
        </>
      }
    >
      <form
        id="employee-form"
        onSubmit={submit}
        className="max-h-[65vh] space-y-6 overflow-y-auto pr-1"
      >
        {error && <Alert>{error}</Alert>}
        <Section title="Identificación">
          {field('first_name', 'Primer nombre', <Input required {...bind('first_name')} />)}
          {field('middle_name', 'Segundo nombre', <Input {...bind('middle_name')} />)}
          {field('last_name', 'Primer apellido', <Input required {...bind('last_name')} />)}
          {field('second_last_name', 'Segundo apellido', <Input {...bind('second_last_name')} />)}
          {field(
            'id_type',
            'Tipo de identificación',
            <Select className="w-full" {...bind('id_type')}>
              <option value="cedula">Cédula</option>
              <option value="passport">Pasaporte</option>
            </Select>,
          )}
          {field(
            'id_number',
            form.id_type === 'cedula' ? 'Cédula' : 'Pasaporte',
            <Input
              required
              placeholder={form.id_type === 'cedula' ? '8-123-4567' : ''}
              {...bind('id_number')}
            />,
          )}
          {field('css_number', 'Nº de seguro social', <Input {...bind('css_number')} />)}
          {field(
            'code',
            'Nº de empleado',
            <Input placeholder={employee ? '' : 'Automático (E-0001…)'} {...bind('code')} />,
          )}
        </Section>

        <Section title="Datos personales">
          {field(
            'birth_date',
            'Fecha de nacimiento',
            <Input type="date" {...bind('birth_date')} />,
          )}
          {field(
            'sex',
            'Sexo',
            <Select className="w-full" {...bind('sex')}>
              <Options
                empty="—"
                items={[
                  ['M', 'Masculino'],
                  ['F', 'Femenino'],
                ]}
              />
            </Select>,
          )}
          {field(
            'marital_status',
            'Estado civil',
            <Select className="w-full" {...bind('marital_status')}>
              <Options empty="—" items={MARITAL_STATUS} />
            </Select>,
          )}
          {field('nationality', 'Nacionalidad', <Input {...bind('nationality')} />)}
        </Section>

        <Section title="Contacto">
          {field('phone', 'Teléfono', <Input type="tel" {...bind('phone')} />)}
          {field('email', 'Correo', <Input type="email" {...bind('email')} />)}
          {field(
            'province',
            'Provincia',
            <Select className="w-full" {...bind('province')}>
              <Options empty="—" items={PROVINCES} />
            </Select>,
          )}
          {field('address', 'Dirección', <Input {...bind('address')} />)}
          {field(
            'emergency_contact_name',
            'Contacto de emergencia',
            <Input {...bind('emergency_contact_name')} />,
          )}
          {field(
            'emergency_contact_phone',
            'Teléfono de emergencia',
            <Input type="tel" {...bind('emergency_contact_phone')} />,
          )}
        </Section>

        <Section title="Empleo y pago">
          {field(
            'hire_date',
            'Fecha de ingreso',
            <Input type="date" required {...bind('hire_date')} />,
          )}
          {field(
            'payment_method',
            'Forma de pago',
            <Select className="w-full" {...bind('payment_method')}>
              <option value="ach">Transferencia ACH</option>
              <option value="check">Cheque</option>
              <option value="cash">Efectivo</option>
            </Select>,
          )}
          {form.payment_method === 'ach' && canSeeBank && (
            <>
              {field(
                'bank',
                'Banco',
                <Select className="w-full" required {...bind('bank')}>
                  <Options empty="Selecciona…" items={BANKS} />
                </Select>,
              )}
              {field(
                'account_type',
                'Tipo de cuenta',
                <Select className="w-full" required {...bind('account_type')}>
                  <Options
                    empty="Selecciona…"
                    items={[
                      ['savings', 'Ahorros'],
                      ['checking', 'Corriente'],
                    ]}
                  />
                </Select>,
              )}
              {field(
                'account_number',
                'Número de cuenta',
                <Input inputMode="numeric" required {...bind('account_number')} />,
              )}
            </>
          )}
          <label className="flex items-center gap-2 self-end pb-2 text-sm">
            <Checkbox
              checked={form.is_union_member}
              onChange={(e) => setForm({ ...form, is_union_member: e.target.checked })}
            />
            Afiliado al sindicato (cuota sindical)
          </label>
        </Section>
        {field('notes', 'Observaciones', <Textarea {...bind('notes')} />)}
      </form>
    </Dialog>
  )
}
