import { NavLink } from 'react-router-dom'
import { useAccess } from '@/features/access/use-access'
import { cn } from '@/lib/utils'

const TABS = [
  { to: '/marcaciones', label: 'Marcaciones', permission: 'timeclock.view', end: true },
  { to: '/marcaciones/importaciones', label: 'Importaciones', permission: 'timeclock.import' },
  { to: '/marcaciones/configuracion', label: 'Relojes y plantillas', permission: 'timeclock.view' },
]

export function TimeclockTabs() {
  const { can } = useAccess()
  return (
    <nav aria-label="Marcaciones" className="flex gap-1 overflow-x-auto overflow-y-hidden border-b">
      {TABS.filter((t) => can(t.permission)).map((t) => (
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
