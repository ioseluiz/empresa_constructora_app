import { Building2, Moon, Sun } from 'lucide-react'
import { useState } from 'react'
import { NavLink, Outlet } from 'react-router-dom'
import { cn } from '@/lib/utils'
import { navigation } from './navigation'

function useTheme() {
  const [dark, setDark] = useState(() => document.documentElement.classList.contains('dark'))
  const toggle = () => {
    const next = !dark
    document.documentElement.classList.toggle('dark', next)
    try {
      localStorage.setItem('theme', next ? 'dark' : 'light')
    } catch {
      /* almacenamiento no disponible */
    }
    setDark(next)
  }
  return { dark, toggle }
}

export function AppLayout() {
  const { dark, toggle } = useTheme()

  return (
    <div className="flex min-h-screen">
      <aside className="bg-sidebar text-sidebar-foreground hidden w-64 shrink-0 flex-col md:flex">
        <div className="flex h-16 items-center gap-2.5 px-5">
          <span className="bg-accent text-sidebar flex size-8 items-center justify-center rounded-md">
            <Building2 className="size-4.5" />
          </span>
          <span className="font-semibold tracking-tight">Constructora</span>
        </div>
        <nav className="flex flex-1 flex-col gap-0.5 px-3 py-2" aria-label="Principal">
          {navigation.map((item) =>
            item.sprint ? (
              <span
                key={item.to}
                className="text-sidebar-muted flex items-center gap-3 rounded-md px-3 py-2 text-sm"
                title="Próximamente"
              >
                <item.icon className="size-4" />
                {item.label}
                <span className="ml-auto text-[10px] tracking-wide uppercase opacity-70">
                  Pronto
                </span>
              </span>
            ) : (
              <NavLink
                key={item.to}
                to={item.to}
                end
                className={({ isActive }) =>
                  cn(
                    'hover:bg-sidebar-active flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors',
                    isActive && 'bg-sidebar-active font-medium',
                  )
                }
              >
                <item.icon className="size-4" />
                {item.label}
              </NavLink>
            ),
          )}
        </nav>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="bg-card flex h-16 items-center justify-between border-b px-4 md:px-8">
          <span className="font-semibold md:hidden">Constructora</span>
          <span className="text-muted-foreground hidden text-sm md:block">Gestión empresarial</span>
          <button
            type="button"
            onClick={toggle}
            className="text-muted-foreground hover:bg-muted rounded-md p-2"
            aria-label={dark ? 'Cambiar a modo claro' : 'Cambiar a modo oscuro'}
          >
            {dark ? <Sun className="size-4" /> : <Moon className="size-4" />}
          </button>
        </header>
        <main className="flex-1 p-4 md:p-8">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
