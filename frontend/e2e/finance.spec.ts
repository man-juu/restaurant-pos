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

test('accountant posts a balanced journal in the books (FR-FIN-002, 004)', async ({ page }) => {
  const posts: { path: string; body: unknown }[] = []
  const accounts = [
    {
      id: 'a-cash',
      code: '1-1100',
      name: 'Cash on hand',
      type: 'asset',
      parent_id: null,
      system_key: 'cash',
      is_active: true,
    },
    {
      id: 'a-rent',
      code: '6-1100',
      name: 'Rent',
      type: 'expense',
      parent_id: null,
      system_key: null,
      is_active: true,
    },
  ]
  await page.route('**/api/v1/**', async (route: Route) => {
    const req = route.request()
    const path = new URL(req.url()).pathname
    if (req.method() !== 'GET') posts.push({ path, body: req.postDataJSON() })
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
        permissions: ['finance.report.view', 'finance.ledger.view', 'finance.journal.create'],
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
      '/api/v1/finance/gl/setup': {
        start_date: '2026-01-01',
        template: 'id_fnb',
        opening_entry_id: null,
      },
      '/api/v1/finance/gl/accounts': accounts,
      '/api/v1/finance/gl/journals': [],
    }
    return path in data
      ? route.fulfill({ json: data[path] })
      : route.fulfill({ status: 404, json: { code: 'not_found' } })
  })
  await page.goto('/finance')
  await page.getByRole('button', { name: 'EN', exact: true }).click()
  await page.getByRole('tab', { name: 'Books' }).click()
  await page.getByRole('button', { name: 'New journal' }).click()
  const accountsBoxes = page.getByLabel('Account')
  await accountsBoxes.nth(0).selectOption('a-rent')
  await accountsBoxes.nth(1).selectOption('a-cash')
  await page.getByLabel('Debit').nth(0).fill('1000000')
  await expect(page.getByRole('button', { name: 'Save journal' })).toBeDisabled() // not balanced yet
  await page.getByLabel('Credit').nth(1).fill('1000000')
  await page.getByRole('button', { name: 'Save journal' }).click()
  await expect
    .poll(() => posts.at(-1)?.body)
    .toMatchObject({
      lines: [
        { account_id: 'a-rent', debit: 1000000, credit: 0 },
        { account_id: 'a-cash', debit: 0, credit: 1000000 },
      ],
    })
})
