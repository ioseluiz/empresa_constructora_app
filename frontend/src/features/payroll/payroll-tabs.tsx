import { NavLink } from 'react-router-dom'
import { useAccess } from '@/features/access/use-access'
import { cn } from '@/lib/utils'

const TABS = [
  { to: '/planilla', label: 'Corridas', end: true },
  { to: '/planilla/global', label: 'Planilla global' },
  { to: '/planilla/simulador', label: 'Simulador' },
  { to: '/planilla/conceptos', label: 'Conceptos' },
  { to: '/planilla/parametros', label: 'Parámetros legales' },
  { to: '/planilla/configuracion', label: 'Configuración' },
]

export function PayrollTabs() {
  const { can } = useAccess()
  if (!can('payroll.view')) return null
  return (
    <nav aria-label="Planilla" className="flex gap-1 overflow-x-auto overflow-y-hidden border-b">
      {TABS.map((t) => (
        <NavLink
          key={t.to}
          to={t.to}
          end={t.end}
          className={({ isActive }) =>
            cn(
              'border-b-2 px-3 py-2 text-sm font-medium whitespace-nowrap transition-colors',
              isActive
                ? 'border-primary text-foreground'
                : 'text-muted-foreground hover:text-foreground border-transparent',
            )
          }
        >
          {t.label}
        </NavLink>
      ))}
    </nav>
  )
}
