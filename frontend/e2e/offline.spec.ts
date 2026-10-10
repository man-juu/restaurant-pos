import { expect, type Route, test } from '@playwright/test'

const SESSION = {
  user: { id: 'u', email: 'o@x', name: 'Rina', locale: 'en' },
  tenants: [{ id: 't', name: 'Dapur' }],
  active_tenant_id: 't',
  csrf_token: 'c',
  mfa_state: 'ok',
}
const CAPS = {
  tenant_id: 't',
  permissions: [
    'sales.order.create',
    'sales.order.pay',
    'catalog.item.view',
    'tenant.settings.view',
  ],
  all_outlets: true,
  outlet_ids: [],
  modules: ['inventory', 'sales'],
  subscription: { state: 'active', days_left: null },
  nav: ['pos'],
  currency: 'IDR',
  language: 'id',
}
const ITEM = {
  id: 'i-tea',
  name: 'Iced tea',
  sku: 'TEA',
  category_id: null,
  photo_upload_id: null,
  is_available: true,
  price: 10000,
  modifier_groups: [],
  combo: [],
}
const CASH = { code: 'cash', name: 'Cash', kind: 'cash', active: true }
const PACK = {
  enabled: true,
  channel_code: 'dine_in',
  tax: { rules: [{ id: 'pbjt', name: 'PBJT', rate_bp: 1000, price_includes_tax: false }] },
  service_charge: { enabled: false },
  cash_rounding_step: 0,
  tips_enabled: false,
  methods: [CASH],
}
const GETS: Record<string, unknown> = {
  '/api/v1/auth/session': SESSION,
  '/api/v1/me/capabilities': CAPS,
  '/api/v1/outlets': [{ id: 'o1', name: 'Shop', type: 'branch', is_active: true }],
  '/api/v1/catalog/channels': [
    { id: 'c1', code: 'dine_in', name: 'Dine-in', kind: 'dine_in', sort_order: 0, is_active: true },
  ],
  '/api/v1/catalog/categories': [],
  '/api/v1/catalog/menu': [ITEM],
  '/api/v1/settings': {
    payment_methods: { methods: [CASH] },
    pos: { require_shift: false, cash_rounding_step: 0, tips_enabled: false },
  },
  '/api/v1/pos/orders': [],
  '/api/v1/pos/offline/pack': PACK,
}

test('an order taken offline uploads once even when the connection cuts mid-upload (FR-SAL-013, Gate 4)', async ({
  page,
}) => {
  const stored = new Map<string, unknown>()
  let attempts = 0
  await page.route('**/api/v1/**', async (route: Route) => {
    const req = route.request()
    const path = new URL(req.url()).pathname
    if (req.method() === 'GET') {
      const data = GETS[path]
      return data === undefined
        ? route.fulfill({ status: 404, json: { code: 'not_found' } })
        : route.fulfill({ json: data })
    }
    if (path !== '/api/v1/pos/offline/orders') return route.fulfill({ status: 404, json: {} })
    attempts += 1
    const body = req.postDataJSON() as { client_id: string; payment: { payments: unknown[] } }
    expect(body.payment.payments).toHaveLength(1)
    // The server keeps the order by client_id, like the real unique constraint.
    if (!stored.has(body.client_id)) stored.set(body.client_id, body)
    if (attempts === 1) return route.abort('connectionreset') // the answer never arrives
    return route.fulfill({
      json: {
        client_id: body.client_id,
        order_id: 'x',
        number: 'POS-1',
        status: 'paid',
        problem: null,
        skipped_lines: 0,
      },
    })
  })
  await page.goto('/pos')
  await page.getByRole('button', { name: 'EN' }).click()
  await page.getByRole('checkbox', { name: 'Work offline' }).check()
  await page.getByRole('button', { name: /Iced tea/ }).click()
  await page.getByRole('button', { name: /Iced tea/ }).click()
  await expect(page.getByText('IDR 22,000')).toBeVisible() // 2 × 10.000 + 10 % tax
  await page.getByLabel('Cash received').fill('50000')
  await expect(page.getByText('Change: IDR 28,000')).toBeVisible()
  await page.getByRole('button', { name: 'Finish order' }).click()
  await expect(page.getByText('1 order waiting to upload')).toBeVisible()

  await page.getByRole('button', { name: 'Upload now' }).click()
  await expect(page.getByText('1 order waiting to upload')).toBeVisible()
  await page.getByRole('button', { name: 'Upload now' }).click()
  await expect(page.getByText('0 orders waiting to upload')).toBeVisible()
  expect(attempts).toBe(2)
  expect(stored.size).toBe(1)
})
