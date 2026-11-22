import { createBrowserRouter, Navigate } from 'react-router-dom'
import { AppLayout } from '@/components/layout/app-layout'
import { ForgotPasswordPage } from '@/features/auth/forgot-password-page'
import { LoginPage } from '@/features/auth/login-page'
import { RedirectIfAuthenticated, RequireAuth } from '@/features/auth/require-auth'
import { ResetPasswordPage } from '@/features/auth/reset-password-page'
import { DashboardPage } from '@/features/dashboard/dashboard-page'

export const router = createBrowserRouter([
  {
    element: <RedirectIfAuthenticated />,
    children: [
      { path: '/login', element: <LoginPage /> },
      { path: '/recuperar-contrasena', element: <ForgotPasswordPage /> },
    ],
  },
  // Accesible con o sin sesión: el enlace llega por correo.
  { path: '/restablecer-contrasena', element: <ResetPasswordPage /> },
  {
    element: <RequireAuth />,
    children: [
      {
        element: <AppLayout />,
        children: [{ index: true, element: <DashboardPage /> }],
      },
    ],
  },
  { path: '*', element: <Navigate to="/" replace /> },
])
