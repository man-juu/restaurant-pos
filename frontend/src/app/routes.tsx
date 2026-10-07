import { AdminPage } from '../features/admin/AdminPage'
import { LoginPage } from '../features/auth/LoginPage'
import { DashboardPage } from '../features/dashboard/DashboardPage'
import { OutletsPage } from '../features/outlets/OutletsPage'
import { Shell } from './Shell'

export const routes = [
  { path: '/login', element: <LoginPage /> },
  { path: '/admin', element: <AdminPage /> },
  {
    path: '/',
    element: <Shell />,
    children: [
      { index: true, element: <DashboardPage /> },
      { path: 'outlets', element: <OutletsPage /> },
      // Module pages arrive with their modules (Phase 1); nav entries come from capabilities.
      { path: '*', element: <DashboardPage /> },
    ],
  },
]
