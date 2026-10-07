/* eslint-disable react-refresh/only-export-components -- route table, not a component module */
import { lazy, Suspense, type ReactNode } from 'react'

import { DashboardPage } from '../features/dashboard/DashboardPage'
import { Shell } from './Shell'

// Rarely used or entry-only screens load on demand, so the main bundle stays small on
// mobile connections (performance budget: scripts/check-bundle.mjs).
const AdminPage = lazy(() =>
  import('../features/admin/AdminPage').then((m) => ({ default: m.AdminPage })),
)
const LoginPage = lazy(() =>
  import('../features/auth/LoginPage').then((m) => ({ default: m.LoginPage })),
)
const SettingsPage = lazy(() =>
  import('../features/settings/SettingsPage').then((m) => ({ default: m.SettingsPage })),
)
const CatalogPage = lazy(() =>
  import('../features/catalog/CatalogPage').then((m) => ({ default: m.CatalogPage })),
)
const InventoryPage = lazy(() =>
  import('../features/inventory/InventoryPage').then((m) => ({ default: m.InventoryPage })),
)
const OutletsPage = lazy(() =>
  import('../features/outlets/OutletsPage').then((m) => ({ default: m.OutletsPage })),
)

const page = (element: ReactNode) => <Suspense fallback={null}>{element}</Suspense>

export const routes = [
  { path: '/login', element: page(<LoginPage />) },
  { path: '/admin', element: page(<AdminPage />) },
  {
    path: '/',
    element: <Shell />,
    children: [
      { index: true, element: <DashboardPage /> },
      { path: 'outlets', element: page(<OutletsPage />) },
      { path: 'settings', element: page(<SettingsPage />) },
      { path: 'catalog', element: page(<CatalogPage />) },
      { path: 'inventory', element: page(<InventoryPage />) },
      // Module pages arrive with their modules (Phase 1); nav entries come from capabilities.
      { path: '*', element: <DashboardPage /> },
    ],
  },
]
