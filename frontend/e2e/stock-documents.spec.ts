import { expect, type Page, test } from '@playwright/test'

type Body = Record<string, unknown>

const rice = {
  id: 'i-rice',
  sku: 'RICE',
  type: 'ingredient',
  name: 'Rice',
  category_id: null,
  base_unit_id: 'u-g',
  is_active: true,
}
const line = { item_id: 'i-rice', sku: 'RICE', name: 'Rice', unit_code: 'g' }
const header = (kind: string, number: string, status: string, extra: Body = {}) => ({
  id: `${kind}-1`,
  kind,
  number,
  outlet_id: 'o1',
  business_date: '2026-02-01',
  status,
  note: null,
  created_by: 'u',
  blind: false,
  ...extra,
})

/** Fake stock-document API with just enough state for waste and a blind count. */
async function mock(page: Page) {
  const calls: { method: string; path: string; body: Body }[] = []
  const state = { waste: [] as Body[], count: undefined as Body | undefined }
  const routes: Record<string, (body: Body) => unknown> = {
    'GET /api/v1/outlets': () => [
      { id: 'o1', name: 'Shop', type: 'branch', timezone: 'Asia/Jakarta', is_active: true },
    ],
    'GET /api/v1/catalog/units': () => [
      { id: 'u-g', code: 'g', name: 'gram', dimension: 'mass', is_platform: true },
    ],
    'GET /api/v1/catalog/items': () => ({ items: [rice], next_cursor: null }),
    'GET /api/v1/inventory/stock': () => ({ items: [], next_cursor: null }),
    'GET /api/v1/inventory/documents/waste': () => state.waste,
    'POST /api/v1/inventory/waste': () => {
      const doc = header('waste', 'WASTE-2026-00001', 'posted', { reason_code: 'spoilage' })
      state.waste.push(doc)
      return doc
    },
    'GET /api/v1/inventory/documents/counts': () => (state.count ? [state.count] : []),
    'POST /api/v1/inventory/counts': () => {
      state.count = header('count', 'CNT-2026-00001', 'draft', {
        count_type: 'full',
        blind: true,
        lines: [{ ...line, system_qty: null, counted_qty: null }],
      })
      return state.count
    },
    'GET /api/v1/inventory/documents/counts/count-1': () => state.count,
    'PUT /api/v1/inventory/counts/count-1/lines': () => state.count,
    'POST /api/v1/inventory/counts/count-1/submit': () => {
      state.count = {
        ...state.count,
        status: 'posted',
        lines: [{ ...line, system_qty: '2500', counted_qty: '2400' }],
      }
      return state.count
    },
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
        permissions: ['inventory.stock.view', 'inventory.waste.create', 'inventory.count.create'],
        all_outlets: true,
        outlet_ids: [],
        modules: ['inventory'],
        subscription: { state: 'active', days_left: null },
        nav: ['inventory'],
        currency: 'IDR',
        language: 'id',
      })
    const body = (req.postDataJSON() ?? {}) as Body
    if (req.method() !== 'GET') calls.push({ method: req.method(), path, body })
    const handler = routes[`${req.method()} ${path}`]
    return handler ? json(handler(body)) : json({ code: 'not_found' }, 404)
  })
  return calls
}

test('kitchen staff log waste and do a blind count (FR-INV-007, 008)', async ({ page }) => {
  const calls = await mock(page)
  await page.goto('/inventory')
  await page.getByRole('button', { name: 'EN' }).click()
  await expect(page.getByRole('tab', { name: 'Adjustments' })).toHaveCount(0) // no permission

  await page.getByRole('tab', { name: 'Waste' }).click()
  await page.getByLabel('Add item').fill('rice')
  await page.getByRole('button', { name: /Rice \(RICE\)/ }).click()
  await page.getByLabel('Quantity').fill('500')
  await page.getByRole('button', { name: 'Record waste' }).click()
  await expect(page.getByText('WASTE-2026-00001')).toBeVisible()
  expect(calls[0].body).toMatchObject({
    reason_code: 'spoilage',
    lines: [{ item_id: 'i-rice', qty: '500', unit_id: 'u-g' }],
  })

  await page.getByRole('tab', { name: 'Stock counts' }).click()
  await page.getByRole('button', { name: 'Start count' }).click()
  await expect(page.getByRole('heading', { name: 'CNT-2026-00001' })).toBeVisible()
  await expect(page.getByText(/System:/)).toHaveCount(0) // blind: no system quantity
  await page.getByLabel('Counted (g)').fill('2400')
  await page.getByRole('button', { name: 'Submit' }).click()
  await expect(page.getByText(/System: 2[.,]500 g/)).toBeVisible()
  expect(calls.map((c) => `${c.method} ${c.path}`).slice(1)).toEqual([
    'POST /api/v1/inventory/counts',
    'PUT /api/v1/inventory/counts/count-1/lines',
    'POST /api/v1/inventory/counts/count-1/submit',
  ])
})
