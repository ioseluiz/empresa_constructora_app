import { createBrowserRouter, Navigate } from 'react-router-dom'
import { AppLayout } from '@/components/layout/app-layout'
import { RequirePermission } from '@/features/access/require-permission'
import { SecurityPage } from '@/features/account/security-page'
import { AcceptInvitationPage } from '@/features/auth/accept-invitation-page'
import { ForgotPasswordPage } from '@/features/auth/forgot-password-page'
import { LoginPage } from '@/features/auth/login-page'
import { RedirectIfAuthenticated, RequireAuth } from '@/features/auth/require-auth'
import { ResetPasswordPage } from '@/features/auth/reset-password-page'
import { DashboardPage } from '@/features/dashboard/dashboard-page'
import { AuditPage } from '@/features/settings/audit-page'
import { CompanyPage } from '@/features/settings/company-page'
import { RolesPage } from '@/features/settings/roles-page'
import { UsersPage } from '@/features/settings/users-page'
import { CbaPage } from '@/features/catalogs/cba-page'
import { CostCentersPage } from '@/features/catalogs/cost-centers-page'
import { HolidaysPage } from '@/features/catalogs/holidays-page'
import { PositionsPage } from '@/features/catalogs/positions-page'
import { ProjectsPage } from '@/features/projects/projects-page'
import { EmployeeDetailPage } from '@/features/employees/employee-detail-page'
import { EmployeesPage } from '@/features/employees/employees-page'
import { BatchPage } from '@/features/timeclock/batch-page'
import { TimeclockConfigPage } from '@/features/timeclock/config-page'
import { ImportsPage } from '@/features/timeclock/imports-page'
import { PunchesPage } from '@/features/timeclock/punches-page'
import { ShiftsPage } from '@/features/timeclock/shifts-page'
import { WorkDaysPage } from '@/features/timeclock/workdays-page'
import { ConceptsPage } from '@/features/payroll/concepts-page'
import { ParametersPage } from '@/features/payroll/parameters-page'
import { PayrollSettingsPage } from '@/features/payroll/settings-page'
import { SimulatorPage } from '@/features/payroll/simulator-page'

function guarded(permission: string, page: React.ReactNode) {
  return <RequirePermission permission={permission}>{page}</RequirePermission>
}

export const router = createBrowserRouter([
  {
    element: <RedirectIfAuthenticated />,
    children: [
      { path: '/login', element: <LoginPage /> },
      { path: '/recuperar-contrasena', element: <ForgotPasswordPage /> },
    ],
  },
  // Accesibles con o sin sesión: los enlaces llegan por correo.
  { path: '/restablecer-contrasena', element: <ResetPasswordPage /> },
  { path: '/aceptar-invitacion', element: <AcceptInvitationPage /> },
  {
    element: <RequireAuth />,
    children: [
      {
        element: <AppLayout />,
        children: [
          { index: true, element: <DashboardPage /> },
          { path: 'cuenta/seguridad', element: <SecurityPage /> },
          { path: 'proyectos', element: guarded('projects.view', <ProjectsPage />) },
          { path: 'empleados', element: guarded('hr.employee.view', <EmployeesPage />) },
          { path: 'marcaciones', element: guarded('timeclock.view', <PunchesPage />) },
          {
            path: 'marcaciones/jornadas',
            element: guarded('timeclock.view', <WorkDaysPage />),
          },
          { path: 'planilla', element: guarded('payroll.view', <SimulatorPage />) },
          { path: 'planilla/conceptos', element: guarded('payroll.view', <ConceptsPage />) },
          { path: 'planilla/parametros', element: guarded('payroll.view', <ParametersPage />) },
          {
            path: 'planilla/configuracion',
            element: guarded('payroll.view', <PayrollSettingsPage />),
          },
          { path: 'marcaciones/horarios', element: guarded('timeclock.view', <ShiftsPage />) },
          {
            path: 'marcaciones/importaciones',
            element: guarded('timeclock.import', <ImportsPage />),
          },
          {
            path: 'marcaciones/importaciones/:id',
            element: guarded('timeclock.import', <BatchPage />),
          },
          {
            path: 'marcaciones/configuracion',
            element: guarded('timeclock.view', <TimeclockConfigPage />),
          },
          {
            path: 'empleados/:id',
            element: guarded('hr.employee.view', <EmployeeDetailPage />),
          },
          {
            path: 'catalogos/centros-de-costo',
            element: guarded('org.manage', <CostCentersPage />),
          },
          { path: 'catalogos/puestos', element: guarded('org.manage', <PositionsPage />) },
          { path: 'catalogos/convencion', element: guarded('org.manage', <CbaPage />) },
          { path: 'catalogos/feriados', element: guarded('org.manage', <HolidaysPage />) },
          {
            path: 'configuracion/empresa',
            element: (
              <RequirePermission permission="tenant.manage">
                <CompanyPage />
              </RequirePermission>
            ),
          },
          {
            path: 'configuracion/usuarios',
            element: (
              <RequirePermission permission="users.view">
                <UsersPage />
              </RequirePermission>
            ),
          },
          {
            path: 'configuracion/roles',
            element: (
              <RequirePermission permission="roles.manage">
                <RolesPage />
              </RequirePermission>
            ),
          },
          {
            path: 'configuracion/auditoria',
            element: (
              <RequirePermission permission="audit.view">
                <AuditPage />
              </RequirePermission>
            ),
          },
        ],
      },
    ],
  },
  { path: '*', element: <Navigate to="/" replace /> },
])
