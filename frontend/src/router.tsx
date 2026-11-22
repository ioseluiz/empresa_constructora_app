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
