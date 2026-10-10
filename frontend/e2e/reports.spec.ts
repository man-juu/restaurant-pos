import { expect, test } from '@playwright/test'

test('manager reads sales by item with margin and can download it (FR-RPT-003)', async ({
  page,
}) => {
  await page.route('**/api/v1/**', async (route) => {
    const path = new URL(route.request().url()).pathname
    const json = (data: unknown, status = 200) => route.fulfill({ status, json: data })
    if (path === '/api/v1/auth/session')
      return json({
        user: { id: 'u', email: 'o@x', name: 'Rina', locale: 'en' },
        tenants: [{ id: 't', name: 'Dapur' }],
        active_tenant_id: 't',
        csrf_token: 'c',
        mfa_state: 'ok',
      })
    if (path === '/api/v1/me/capabilities')
      return json({
        tenant_id: 't',
        permissions: ['sales.report.view'],
        all_outlets: true,
        outlet_ids: [],
        modules: ['sales'],
        subscription: { state: 'active', days_left: null },
        nav: ['reports'],
        currency: 'IDR',
        language: 'id',
      })
    if (path === '/api/v1/outlets') return json([])
    if (path === '/api/v1/sales/reports/breakdown')
      return json({
        columns: ['name', 'qty', 'net_sales', 'food_cost', 'food_cost_pct', 'margin'],
        rows: [
          {
            name: 'Nasi goreng',
            qty: '10',
            net_sales: 225000,
            food_cost: 68000,
            food_cost_pct: '30.2',
            margin: 157000,
          },
        ],
        computed_at: '2026-10-09T03:00:00Z',
        totals: {},
      })
    if (path === '/api/v1/sales/reports/summary')
      return json({
        columns: ['period'],
        rows: [],
        computed_at: '2026-10-09T03:00:00Z',
        totals: {},
      })
    return json({}, 404)
  })
  await page.goto('/reports')
  await page.getByRole('button', { name: 'EN' }).click()
  await page.getByLabel('Report').selectOption({ label: 'Sales and margin by item' })
  await expect(page.getByRole('cell', { name: 'Nasi goreng' })).toBeVisible()
  await expect(page.getByRole('cell', { name: '30.2 %' })).toBeVisible()
  await expect(page.getByRole('columnheader', { name: 'Gross margin' })).toBeVisible()
  const csv = page.getByRole('link', { name: 'Download CSV' })
  await expect(csv).toHaveAttribute('href', /format=csv&by=item/)
})
