import {
  Building,
  CalendarDays,
  Clock,
  FileText,
  HardHat,
  History,
  LayoutDashboard,
  ShieldCheck,
  Users,
  UsersRound,
  Wallet,
  type LucideIcon,
} from 'lucide-react'

export interface NavItem {
  label: string
  to: string
  icon: LucideIcon
  permission?: string // permiso requerido para mostrarlo
  sprint?: number // sprint del plan en que se habilita (docs/PLAN.md §6)
}

export interface NavSection {
  title?: string
  items: NavItem[]
}

export const navigation: NavSection[] = [
  {
    items: [
      { label: 'Inicio', to: '/', icon: LayoutDashboard },
      { label: 'Proyectos', to: '/proyectos', icon: HardHat, sprint: 4 },
      { label: 'Empleados', to: '/empleados', icon: Users, sprint: 5 },
      { label: 'Marcaciones', to: '/marcaciones', icon: Clock, sprint: 6 },
      { label: 'Planilla', to: '/planilla', icon: Wallet, sprint: 8 },
      { label: 'Vacaciones', to: '/vacaciones', icon: CalendarDays, sprint: 11 },
      { label: 'Reportes', to: '/reportes', icon: FileText, sprint: 10 },
    ],
  },
  {
    title: 'Configuración',
    items: [
      {
        label: 'Empresa',
        to: '/configuracion/empresa',
        icon: Building,
        permission: 'tenant.manage',
      },
      {
        label: 'Usuarios',
        to: '/configuracion/usuarios',
        icon: UsersRound,
        permission: 'users.view',
      },
      { label: 'Roles', to: '/configuracion/roles', icon: ShieldCheck, permission: 'roles.manage' },
      {
        label: 'Auditoría',
        to: '/configuracion/auditoria',
        icon: History,
        permission: 'audit.view',
      },
    ],
  },
]
