import { expect, type Route, test } from '@playwright/test'

test('accountant sees profit and loss with expenses by category (FR-FIN-001)', async ({ page }) => {
  await page.route('**/api/v1/**', async (route: Route) => {
    const path = new URL(route.request().url()).pathname
    const data: Record<string, unknown> = {
      '/api/v1/auth/session': {
        user: { id: 'u', email: 'a@x', name: 'Dewi', locale: 'en' },
        tenants: [{ id: 't', name: 'Dapur' }],
        active_tenant_id: 't',
        csrf_token: 'c',
        mfa_state: 'ok',
      },
      '/api/v1/me/capabilities': {
        tenant_id: 't',
        permissions: ['finance.report.view', 'finance.expense.view'],
        all_outlets: true,
        outlet_ids: [],
        modules: ['finance'],
        subscription: { state: 'active', days_left: null },
        nav: ['finance'],
        currency: 'IDR',
        language: 'id',
      },
      '/api/v1/outlets': [
        { id: 'o1', name: 'Shop', type: 'branch', timezone: 'Asia/Jakarta', is_active: true },
      ],
      '/api/v1/finance/profit-loss': {
        net_sales: 50000,
        service_charge: 0,
        revenue: 50000,
        cost_of_sales: 12000,
        gross_profit: 38000,
        expenses: { Gas: 30000 },
        expenses_total: 30000,
        net_profit: 8000,
        tax_collected: 5000,
      },
    }
    return path in data
      ? route.fulfill({ json: data[path] })
      : route.fulfill({ status: 404, json: { code: 'not_found' } })
  })
  await page.goto('/finance')
  await page.getByRole('button', { name: 'EN' }).click()
  await expect(page.getByText('Gross profit')).toBeVisible()
  await expect(page.getByText('Gas')).toBeVisible()
  await expect(page.getByText(/8[.,]000/).first()).toBeVisible()
})
