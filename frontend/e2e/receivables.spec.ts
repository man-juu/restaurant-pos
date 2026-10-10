import { expect, type Route, test } from '@playwright/test'

test('accountant sees aging and records a customer payment (FR-SAL-011, FR-FIN-006)', async ({
  page,
}) => {
  const posts: { path: string; body: unknown }[] = []
  const invoice = {
    id: 'r1',
    document_id: 'd1',
    number: 'INV-000001',
    customer_id: 'c1',
    customer_name: 'Warung Bu Sri',
    outlet_id: 'o1',
    invoice_date: '2026-03-02',
    due_date: '2026-03-16',
    subtotal: 20000,
    tax: 0,
    total: 20000,
    paid: 0,
    balance: 20000,
    status: 'open',
    lines: [],
  }
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
        permissions: ['finance.report.view', 'sales.invoice.view', 'sales.invoice.manage'],
        all_outlets: true,
        outlet_ids: [],
        modules: ['finance', 'sales'],
        subscription: { state: 'active', days_left: null },
        nav: ['finance'],
        currency: 'IDR',
        language: 'id',
      },
      '/api/v1/outlets': [
        { id: 'o1', name: 'Shop', type: 'branch', timezone: 'Asia/Jakarta', is_active: true },
      ],
      '/api/v1/settings': {
        payment_methods: { methods: [{ code: 'transfer', kind: 'bank', active: true }] },
      },
      '/api/v1/sales/invoices': [invoice],
      '/api/v1/sales/invoices/aging': [
        {
          party_id: 'c1',
          party_name: 'Warung Bu Sri',
          current: 0,
          days_1_30: 20000,
          days_31_60: 0,
          days_61_90: 0,
          over_90: 0,
          total: 20000,
        },
      ],
      '/api/v1/sales/invoices/r1/payments': { ...invoice, paid: 20000, balance: 0, status: 'paid' },
    }
    return path in data
      ? route.fulfill({ json: data[path] })
      : route.fulfill({ status: 404, json: { code: 'not_found' } })
  })
  await page.goto('/finance')
  await page.getByRole('button', { name: 'EN', exact: true }).click()
  await page.getByRole('tab', { name: 'Receivables' }).click()
  await expect(page.getByText('Customers owe us')).toBeVisible()
  await expect(page.getByText('INV-000001 · Warung Bu Sri')).toBeVisible()
  await page.getByRole('button', { name: 'Record payment' }).click()
  await expect
    .poll(() => posts.at(-1))
    .toMatchObject({
      path: '/api/v1/sales/invoices/r1/payments',
      body: { amount: 20000, method: 'transfer' },
    })
})

test('accountant records a platform payout and sees what is unsettled (FR-FIN-007)', async ({
  page,
}) => {
  const posts: { path: string; body: unknown }[] = []
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
        permissions: ['finance.report.view', 'finance.settlement.manage'],
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
      '/api/v1/catalog/channels': [
        { id: 'ch1', code: 'gofood', name: 'GoFood', kind: 'platform', platform: 'gofood' },
      ],
      '/api/v1/finance/accounts': [
        { id: 'b1', name: 'BCA', kind: 'bank', is_active: true, balance: 0, opening_balance: 0 },
      ],
      '/api/v1/finance/settlements': [],
      '/api/v1/finance/settlements/reconcile': {
        orders: 4,
        booked_gross: 110000,
        settled_gross: 0,
        difference: 110000,
        commission: 0,
        fees: 0,
        adjustments: 0,
        payout: 0,
        commission_pct: null,
        settlements: 0,
      },
    }
    return path in data
      ? route.fulfill({ json: data[path] })
      : route.fulfill({ status: 404, json: { code: 'not_found' } })
  })
  await page.goto('/finance')
  await page.getByRole('button', { name: 'EN', exact: true }).click()
  await page.getByRole('tab', { name: 'Platform payouts' }).click()
  await expect(page.getByText(/Not yet settled/)).toBeVisible()
  await page.getByRole('button', { name: 'Record payout' }).click()
  await page.getByLabel('Gross sales on the statement').fill('110000')
  await page.getByLabel('Commission').fill('22000')
  await expect(page.getByText(/Payout: .*88[.,]000/)).toBeVisible()
  await page.getByRole('button', { name: 'Save payout' }).click()
  await expect
    .poll(() => posts.at(-1)?.body)
    .toMatchObject({ channel_id: 'ch1', account_id: 'b1', gross: 110000, payout: 88000 })
})
