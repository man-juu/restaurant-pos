import { expect, type Page, test } from '@playwright/test'

type Body = Record<string, unknown>

const day = (docs: Body[], status = 'open') => ({
  outlet_id: 'o1',
  business_date: new Date().toISOString().slice(0, 10),
  status,
  documents: docs,
})

async function mock(page: Page) {
  const sent: Body[] = []
  let current = day([])
  await page.route('**/api/v1/**', async (route) => {
    const req = route.request()
    const path = new URL(req.url()).pathname
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
        permissions: ['sales.day.view', 'sales.day.enter', 'catalog.item.view'],
        all_outlets: true,
        outlet_ids: [],
        modules: ['inventory', 'sales'],
        subscription: { state: 'active', days_left: null },
        nav: ['sales'],
        currency: 'IDR',
        language: 'id',
      })
    if (path === '/api/v1/outlets')
      return json([
        { id: 'o1', name: 'Shop', type: 'branch', timezone: 'Asia/Jakarta', is_active: true },
      ])
    if (path === '/api/v1/catalog/channels')
      return json([
        {
          id: 'c1',
          code: 'gofood',
          name: 'GoFood',
          kind: 'platform',
          platform: 'gofood',
          sort_order: 0,
          is_active: true,
        },
      ])
    if (path === '/api/v1/catalog/prices')
      return json({
        items: [{ item_id: 'i-nasi', valid_from: '2026-01-01', price: 25000 }],
        next_cursor: null,
      })
    if (path === '/api/v1/catalog/items')
      return json({
        items: [
          {
            id: 'i-nasi',
            sku: 'NASI',
            type: 'menu',
            name: 'Nasi goreng',
            category_id: null,
            base_unit_id: 'u',
            is_active: true,
          },
        ],
        next_cursor: null,
      })
    if (path === '/api/v1/sales/days/entries') {
      sent.push(req.postDataJSON() as Body)
      current = day([
        {
          id: 'd1',
          number: 'SD-2026-00001',
          outlet_id: 'o1',
          channel_id: 'c1',
          business_date: '2026-03-05',
          status: 'posted',
          subtotal: 250000,
          discount: 25000,
          service_charge: 0,
          tax: 22500,
          total: 247500,
          cost: null,
          created_at: '2026-03-05T10:00:00Z',
          lines: [],
        },
      ])
      return json(current, 201)
    }
    if (path.startsWith('/api/v1/sales/days/')) return json(current)
    return json({}, 404)
  })
  return sent
}

test('cashier enters a GoFood day with a promo (FR-SAL-002)', async ({ page }) => {
  const sent = await mock(page)
  await page.goto('/sales')
  await page.getByRole('button', { name: 'EN' }).click()
  await page.getByLabel(/^Nasi goreng/).fill('10')
  await expect(page.getByText(/At list prices: .*250[.,]000/)).toBeVisible()
  await page.getByLabel(/Total reported by the platform/).fill('225000')
  await page.getByRole('button', { name: "Save this channel's sales" }).click()
  await expect(page.getByText('SD-2026-00001 · GoFood')).toBeVisible()
  expect(sent[0]).toMatchObject({
    channel_id: 'c1',
    lines: [{ item_id: 'i-nasi', qty: '10' }],
    reported_total: 225000,
  })
})
