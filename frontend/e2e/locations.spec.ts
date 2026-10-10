import { expect, type Page, test } from '@playwright/test'

type Body = Record<string, unknown>
const line = { item_id: 'i-beef', sku: 'BEEF', name: 'Beef', unit_code: 'g' }
const count = {
  id: 'count-1',
  kind: 'count',
  number: 'CNT-2026-00002',
  outlet_id: 'o1',
  business_date: '2026-02-01',
  status: 'draft',
  note: null,
  created_by: 'u',
  count_type: 'full',
  blind: false,
  location_id: 'loc-1',
  lines: [{ ...line, system_qty: '1000', counted_qty: null }],
}

async function mock(page: Page) {
  const calls: { method: string; path: string; body: Body }[] = []
  const routes: Record<string, () => unknown> = {
    'GET /api/v1/outlets': () => [
      { id: 'o1', name: 'Shop', type: 'branch', timezone: 'Asia/Jakarta', is_active: true },
    ],
    'GET /api/v1/inventory/stock': () => ({ items: [], next_cursor: null }),
    'GET /api/v1/inventory/locations': () => [
      { id: 'loc-1', outlet_id: 'o1', name: 'Freezer', sort_order: 0, is_active: true },
    ],
    'GET /api/v1/inventory/locations/homes': () => [
      { item_id: 'i-beef', location_id: 'loc-1', sku: 'BEEF', name: 'Beef' },
    ],
    'POST /api/v1/inventory/locations': () => ({
      id: 'loc-2',
      outlet_id: 'o1',
      name: 'Dry store',
      sort_order: 0,
      is_active: true,
    }),
    'GET /api/v1/inventory/documents/counts': () => [],
    'POST /api/v1/inventory/counts': () => count,
    'GET /api/v1/inventory/documents/counts/count-1': () => count,
    'GET /api/v1/inventory/scan': () => ({
      kind: 'batch',
      item_id: 'i-beef',
      sku: 'BEEF',
      name: 'Beef',
      unit_code: 'g',
      base_unit_id: 'u-g',
      batch_id: 'b1',
      lot_code: 'L-7',
      expiry_date: null,
    }),
  }
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
        permissions: ['inventory.stock.view', 'inventory.count.create', 'inventory.level.manage'],
        all_outlets: true,
        outlet_ids: [],
        modules: ['inventory'],
        subscription: { state: 'active', days_left: null },
        nav: ['inventory'],
        currency: 'IDR',
        language: 'id',
      })
    if (req.method() !== 'GET')
      calls.push({ method: req.method(), path, body: (req.postDataJSON() ?? {}) as Body })
    const handler = routes[`${req.method()} ${path}`]
    return handler ? json(handler()) : json({ code: 'not_found' }, 404)
  })
  return calls
}

test('storage places, a count at one place and scanning a label (FR-INV-017, 019)', async ({
  page,
}) => {
  const calls = await mock(page)
  await page.goto('/inventory')
  await page.getByRole('button', { name: 'EN', exact: true }).click()
  await page.getByRole('tab', { name: 'Locations' }).click()
  await expect(page.getByRole('heading', { name: 'Freezer' })).toBeVisible()
  await expect(page.getByText('Beef')).toBeVisible()
  await page.getByLabel('New storage place').fill('Dry store')
  await page.getByRole('button', { name: 'Add place' }).click()
  await expect.poll(() => calls.at(-1)?.body).toMatchObject({ outlet_id: 'o1', name: 'Dry store' })

  await page.getByRole('tab', { name: 'Stock counts' }).click()
  await page.getByLabel('Count at').selectOption('loc-1')
  await page.getByRole('button', { name: 'Start count' }).click()
  await expect(page.getByRole('heading', { name: 'CNT-2026-00002' })).toBeVisible()
  expect(calls.at(-1)?.body).toMatchObject({ location_id: 'loc-1', count_type: 'full' })
  await page.getByLabel('Scan or type a code').fill('B:b1')
  await page.getByRole('button', { name: 'Find' }).click()
  await expect(page.getByLabel('Counted (g)')).toBeFocused()
})
