import {
  CalendarDays,
  Clock,
  FileText,
  HardHat,
  LayoutDashboard,
  Users,
  Wallet,
  type LucideIcon,
} from 'lucide-react'

export interface NavItem {
  label: string
  to: string
  icon: LucideIcon
  sprint?: number // sprint del plan en que se habilita (docs/PLAN.md §6)
}

export const navigation: NavItem[] = [
  { label: 'Inicio', to: '/', icon: LayoutDashboard },
  { label: 'Proyectos', to: '/proyectos', icon: HardHat, sprint: 4 },
  { label: 'Empleados', to: '/empleados', icon: Users, sprint: 5 },
  { label: 'Marcaciones', to: '/marcaciones', icon: Clock, sprint: 6 },
  { label: 'Planilla', to: '/planilla', icon: Wallet, sprint: 8 },
  { label: 'Vacaciones', to: '/vacaciones', icon: CalendarDays, sprint: 11 },
  { label: 'Reportes', to: '/reportes', icon: FileText, sprint: 10 },
]
