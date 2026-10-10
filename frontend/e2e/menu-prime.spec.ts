import { expect, type Page, test } from '@playwright/test'

async function mock(page: Page, puts: unknown[]) {
  await page.route('**/api/v1/**', async (route) => {
    const req = route.request()
    const path = new URL(req.url()).pathname
    const json = (data: unknown, status = 200) => route.fulfill({ status, json: data })
    if (req.method() === 'PUT') {
      puts.push(req.postDataJSON())
      return route.fulfill({ status: 204 })
    }
    const data: Record<string, unknown> = {
      '/api/v1/auth/session': {
        user: { id: 'u', email: 'o@x', name: 'Rina', locale: 'en' },
        tenants: [{ id: 't', name: 'Dapur' }],
        active_tenant_id: 't',
        csrf_token: 'c',
        mfa_state: 'ok',
      },
      '/api/v1/me/capabilities': {
        tenant_id: 't',
        permissions: [
          'sales.report.view',
          'catalog.cost.view',
          'finance.report.view',
          'finance.expense.create',
          'finance.budget.manage',
        ],
        all_outlets: true,
        outlet_ids: [],
        modules: ['sales', 'finance'],
        subscription: { state: 'active', days_left: null },
        nav: ['reports', 'finance'],
        currency: 'IDR',
        language: 'id',
      },
      '/api/v1/settings': { finance: { auto_journals: true, mode: 'advanced' } },
      '/api/v1/outlets': [
        { id: 'o1', name: 'Shop', type: 'branch', timezone: 'Asia/Jakarta', is_active: true },
      ],
      '/api/v1/sales/reports/menu-engineering': {
        columns: ['name', 'qty', 'net_sales', 'unit_margin', 'total_margin', 'mix_pct', 'class'],
        rows: [
          {
            name: 'Nasi goreng',
            qty: '120',
            net_sales: 3600000,
            unit_margin: 19000,
            total_margin: 2280000,
            mix_pct: '41.0',
            class: 'star',
          },
          {
            name: 'Sop buntut',
            qty: '6',
            net_sales: 390000,
            unit_margin: 30000,
            total_margin: 180000,
            mix_pct: '2.1',
            class: 'puzzle',
          },
        ],
        computed_at: '2026-10-09T03:00:00Z',
        totals: { items: 2, popularity_bar_pct: '35.0', average_unit_margin: 19500 },
      },
      '/api/v1/finance/prime-cost': {
        net_sales: 50000000,
        food_cost: 16000000,
        labor: 12000000,
        prime_cost: 28000000,
        prime_cost_pct: '56.0',
        food_cost_pct: '32.0',
        labor_pct: '24.0',
        labor_months_missing: [],
      },
      '/api/v1/finance/budgets/vs-actual': {
        lines: [
          {
            line: 'net_sales',
            budget: 60000000,
            actual: 50000000,
            variance: -10000000,
            variance_pct: '-16.7',
            favourable: false,
          },
          {
            line: 'net_profit',
            budget: 20000000,
            actual: 22000000,
            variance: 2000000,
            variance_pct: '10.0',
            favourable: true,
          },
        ],
        months_missing: ['2026-11-01'],
      },
    }
    return path in data ? json(data[path]) : json({ code: 'not_found' }, 404)
  })
}

test('manager sees menu classes (FR-RPT-007)', async ({ page }) => {
  await mock(page, [])
  await page.goto('/reports')
  await page.getByRole('button', { name: 'EN', exact: true }).click()
  await page.getByLabel('Report').selectOption({ label: 'Menu engineering' })
  await expect(page.getByText('Star: keep and feature')).toBeVisible()
  await expect(page.getByText('Puzzle: profitable, promote')).toBeVisible()
})

test('accountant enters labour and reads prime cost (FR-RPT-008)', async ({ page }) => {
  const puts: unknown[] = []
  await mock(page, puts)
  await page.goto('/finance')
  await page.getByRole('button', { name: 'EN', exact: true }).click()
  await page.getByRole('tab', { name: 'Prime cost' }).click()
  await expect(page.getByText(/56\.0 %/)).toBeVisible()
  await page.getByLabel('Amount (IDR)').fill('12000000')
  await page.getByRole('button', { name: 'Save labour' }).click()
  await expect.poll(() => puts.at(-1)).toMatchObject({ outlet_id: 'o1', amount: 12000000 })
})

test('accountant sets a budget and reads actual vs budget (FR-FIN-010)', async ({ page }) => {
  const puts: unknown[] = []
  await mock(page, puts)
  await page.goto('/finance')
  await page.getByRole('button', { name: 'EN', exact: true }).click()
  await page.getByRole('tab', { name: 'Budget' }).click()
  await expect(page.getByText(/-16\.7 %/)).toBeVisible()
  await expect(page.getByText('No budget for: 2026-11')).toBeVisible()
  await page.getByLabel('Net sales (IDR)').fill('60000000')
  await page.getByRole('button', { name: 'Save budget' }).click()
  await expect
    .poll(() => puts.at(-1))
    .toMatchObject({ outlet_id: 'o1', net_sales: 60000000, labor: 0 })
})
