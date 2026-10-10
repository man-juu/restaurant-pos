/** Every report the screen offers: where it lives, its options, and who may see it. */
export interface ReportDef {
  key: string
  path: string
  permission: string
  params?: Record<string, string>
}

export const REPORTS: ReportDef[] = [
  {
    key: 'salesDaily',
    path: '/api/v1/sales/reports/summary',
    permission: 'sales.report.view',
    params: { grain: 'day' },
  },
  {
    key: 'salesMonthly',
    path: '/api/v1/sales/reports/summary',
    permission: 'sales.report.view',
    params: { grain: 'month' },
  },
  {
    key: 'salesByItem',
    path: '/api/v1/sales/reports/breakdown',
    permission: 'sales.report.view',
    params: { by: 'item' },
  },
  {
    key: 'salesByCategory',
    path: '/api/v1/sales/reports/breakdown',
    permission: 'sales.report.view',
    params: { by: 'category' },
  },
  {
    key: 'salesByChannel',
    path: '/api/v1/sales/reports/breakdown',
    permission: 'sales.report.view',
    params: { by: 'channel' },
  },
  {
    key: 'salesByOutlet',
    path: '/api/v1/sales/reports/breakdown',
    permission: 'sales.report.view',
    params: { by: 'outlet' },
  },
  {
    key: 'salesByWeekday',
    path: '/api/v1/sales/reports/breakdown',
    permission: 'sales.report.view',
    params: { by: 'weekday' },
  },
  {
    key: 'taxCollected',
    path: '/api/v1/sales/reports/tax',
    permission: 'sales.report.view',
  },
  {
    key: 'salesByStaff',
    path: '/api/v1/sales/reports/staff',
    permission: 'sales.staff.view',
  },
  {
    key: 'menuEngineering',
    path: '/api/v1/sales/reports/menu-engineering',
    permission: 'catalog.cost.view', // margins are costs; also needs sales.report.view
  },
  {
    key: 'stockMovements',
    path: '/api/v1/inventory/reports/movements',
    permission: 'inventory.report.view',
  },
  {
    key: 'stockWaste',
    path: '/api/v1/inventory/reports/waste',
    permission: 'inventory.report.view',
  },
  {
    key: 'stockExpiry',
    path: '/api/v1/inventory/reports/expiry',
    permission: 'inventory.report.view',
  },
  {
    key: 'stockVariance',
    path: '/api/v1/inventory/reports/variance',
    permission: 'inventory.report.view',
  },
  {
    key: 'purchasesByVendor',
    path: '/api/v1/purchasing/reports/purchases',
    permission: 'purchasing.report.view',
    params: { by: 'vendor' },
  },
  {
    key: 'purchasesByItem',
    path: '/api/v1/purchasing/reports/purchases',
    permission: 'purchasing.report.view',
    params: { by: 'item' },
  },
]

export interface Filters {
  from: string
  to: string
  outletId: string
  lang: string
}

export function reportUrl(def: ReportDef, f: Filters, format = 'json'): string {
  const q = new URLSearchParams({
    from: f.from,
    to: f.to,
    lang: f.lang.slice(0, 2),
    format,
    ...def.params,
  })
  if (f.outletId) q.set('outlet_id', f.outletId)
  return `${def.path}?${q.toString()}`
}
