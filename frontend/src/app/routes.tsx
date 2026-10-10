/* eslint-disable react-refresh/only-export-components -- route table, not a component module */
import { lazy, Suspense, type ReactNode } from 'react'

import { DashboardPage } from '../features/dashboard/DashboardPage'
import { Shell } from './Shell'

// Rarely used or entry-only screens load on demand, so the main bundle stays small on
// mobile connections (performance budget: scripts/check-bundle.mjs).
const AdminPage = lazy(() =>
  import('../features/admin/AdminPage').then((m) => ({ default: m.AdminPage })),
)
const ChangelogPage = lazy(() =>
  import('../features/help/ChangelogPage').then((m) => ({ default: m.ChangelogPage })),
)
const BookPage = lazy(() =>
  import('../features/booking/BookPage').then((m) => ({ default: m.BookPage })),
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
const PurchasingPage = lazy(() =>
  import('../features/purchasing/PurchasingPage').then((m) => ({ default: m.PurchasingPage })),
)
const ProductionPage = lazy(() =>
  import('../features/production/ProductionPage').then((m) => ({ default: m.ProductionPage })),
)
const TransfersPage = lazy(() =>
  import('../features/transfers/TransfersPage').then((m) => ({ default: m.TransfersPage })),
)
const NotificationsPage = lazy(() =>
  import('../features/notifications/NotificationsPage').then((m) => ({
    default: m.NotificationsPage,
  })),
)
const LoyaltyPage = lazy(() =>
  import('../features/loyalty/LoyaltyPage').then((m) => ({ default: m.LoyaltyPage })),
)
const PosPage = lazy(() => import('../features/pos/PosPage').then((m) => ({ default: m.PosPage })))
const TablesPage = lazy(() =>
  import('../features/tables/TablesPage').then((m) => ({ default: m.TablesPage })),
)
const KitchenPage = lazy(() =>
  import('../features/kitchen/KitchenPage').then((m) => ({ default: m.KitchenPage })),
)
const FinancePage = lazy(() =>
  import('../features/finance/FinancePage').then((m) => ({ default: m.FinancePage })),
)
const SalesPage = lazy(() =>
  import('../features/sales/SalesPage').then((m) => ({ default: m.SalesPage })),
)
const ReportsPage = lazy(() =>
  import('../features/reports/ReportsPage').then((m) => ({ default: m.ReportsPage })),
)
const AuditPage = lazy(() =>
  import('../features/audit/AuditPage').then((m) => ({ default: m.AuditPage })),
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
  { path: '/book/:token', element: page(<BookPage />) },
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
      { path: 'purchasing', element: page(<PurchasingPage />) },
      { path: 'production', element: page(<ProductionPage />) },
      { path: 'transfers', element: page(<TransfersPage />) },
      { path: 'notifications', element: page(<NotificationsPage />) },
      { path: 'pos', element: page(<PosPage />) },
      { path: 'tables', element: page(<TablesPage />) },
      { path: 'loyalty', element: page(<LoyaltyPage />) },
      { path: 'kitchen', element: page(<KitchenPage />) },
      { path: 'finance', element: page(<FinancePage />) },
      { path: 'sales', element: page(<SalesPage />) },
      { path: 'reports', element: page(<ReportsPage />) },
      { path: 'audit', element: page(<AuditPage />) },
      { path: 'changelog', element: page(<ChangelogPage />) },
      // Module pages arrive with their modules (Phase 1); nav entries come from capabilities.
      { path: '*', element: <DashboardPage /> },
    ],
  },
]
