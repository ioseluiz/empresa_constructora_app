import {
  BriefcaseBusiness,
  Building,
  CalendarCheck,
  Network,
  Scale,
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
      { label: 'Proyectos', to: '/proyectos', icon: HardHat, permission: 'projects.view' },
      { label: 'Empleados', to: '/empleados', icon: Users, permission: 'hr.employee.view' },
      { label: 'Marcaciones', to: '/marcaciones', icon: Clock, permission: 'timeclock.view' },
      { label: 'Planilla', to: '/planilla', icon: Wallet, permission: 'payroll.view' },
      { label: 'Vacaciones', to: '/vacaciones', icon: CalendarDays, sprint: 11 },
      { label: 'Reportes', to: '/reportes', icon: FileText, permission: 'payroll.reports' },
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
  {
    title: 'Catálogos',
    items: [
      {
        label: 'Centros de costo',
        to: '/catalogos/centros-de-costo',
        icon: Network,
        permission: 'org.manage',
      },
      {
        label: 'Puestos',
        to: '/catalogos/puestos',
        icon: BriefcaseBusiness,
        permission: 'org.manage',
      },
      { label: 'Convención', to: '/catalogos/convencion', icon: Scale, permission: 'org.manage' },
      {
        label: 'Feriados',
        to: '/catalogos/feriados',
        icon: CalendarCheck,
        permission: 'org.manage',
      },
    ],
  },
]
