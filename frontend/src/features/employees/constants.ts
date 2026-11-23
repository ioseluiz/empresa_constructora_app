type Variant = 'success' | 'neutral' | 'danger'

export const EMPLOYEE_STATUS: Record<string, { label: string; variant: Variant }> = {
  active: { label: 'Activo', variant: 'success' },
  terminated: { label: 'Retirado', variant: 'neutral' },
}

export const CONTRACT_STATUS: Record<string, { label: string; variant: Variant }> = {
  active: { label: 'Vigente', variant: 'success' },
  ended: { label: 'Terminado', variant: 'neutral' },
  cancelled: { label: 'Anulado', variant: 'danger' },
}

export const CONTRACT_TYPES: [string, string][] = [
  ['indefinite', 'Tiempo indefinido'],
  ['fixed_term', 'Tiempo definido'],
  ['project', 'Obra determinada'],
]

export const PAY_FREQUENCIES: [string, string][] = [
  ['weekly', 'Semanal'],
  ['biweekly', 'Quincenal'],
  ['monthly', 'Mensual'],
]

export const PAY_BASES: [string, string][] = [
  ['monthly', 'Salario mensual'],
  ['hourly', 'Por hora'],
]

export const SHIFTS: [string, string][] = [
  ['day', 'Diurna (8 h)'],
  ['night', 'Nocturna (7 h)'],
  ['mixed', 'Mixta (7.5 h)'],
]

export const BANKS: [string, string][] = [
  ['banco_general', 'Banco General'],
  ['banistmo', 'Banistmo'],
  ['bac', 'BAC Credomatic'],
  ['banconal', 'Banco Nacional de Panamá'],
  ['caja_ahorros', 'Caja de Ahorros'],
  ['global_bank', 'Global Bank'],
  ['multibank', 'Multibank'],
  ['banesco', 'Banesco'],
  ['davivienda', 'Davivienda'],
  ['credicorp', 'Credicorp Bank'],
  ['scotiabank', 'Scotiabank'],
  ['banco_aliado', 'Banco Aliado'],
  ['st_georges', 'St. Georges Bank'],
  ['towerbank', 'Towerbank'],
  ['banisi', 'Banisi'],
  ['other', 'Otro'],
]

export const MARITAL_STATUS: [string, string][] = [
  ['single', 'Soltero(a)'],
  ['married', 'Casado(a)'],
  ['union', 'Unido(a)'],
  ['divorced', 'Divorciado(a)'],
  ['widowed', 'Viudo(a)'],
]

export const DOCUMENT_KINDS: [string, string][] = [
  ['id_copy', 'Copia de cédula o pasaporte'],
  ['css_card', 'Carné del seguro social'],
  ['contract', 'Contrato firmado'],
  ['work_permit', 'Permiso de trabajo'],
  ['certificate', 'Certificado o diploma'],
  ['medical', 'Certificado médico'],
  ['other', 'Otro'],
]

/** Misma regla que el backend (apps/organization/panama.py → CEDULA_REGEX). */
export const CEDULA_PATTERN = /^(?:(?:[1-9]|1[0-3])(?:AV|PI)?|PE|E|N)-\d{1,4}-\d{1,6}$/

export function todayISO() {
  const d = new Date()
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}
