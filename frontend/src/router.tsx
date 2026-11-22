import { createBrowserRouter } from 'react-router-dom'
import { AppLayout } from '@/components/layout/app-layout'
import { DashboardPage } from '@/features/dashboard/dashboard-page'

export const router = createBrowserRouter([
  {
    element: <AppLayout />,
    children: [{ index: true, element: <DashboardPage /> }],
  },
])
