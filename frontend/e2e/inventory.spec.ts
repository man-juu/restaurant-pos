import { expect, type Page, test } from '@playwright/test'

type Body = Record<string, unknown>

const units = [
  { id: 'u-g', code: 'g', name: 'gram', dimension: 'mass', is_platform: true },
  { id: 'u-kg', code: 'kg', name: 'kilogram', dimension: 'mass', is_platform: true },
]
const rice = {
  id: 'i-rice',
  sku: 'RICE',
  type: 'ingredient',
  name: 'Rice',
  category_id: null,
  base_unit_id: 'u-g',
  is_active: true,
}

/** Fake inventory API: posting opening stock fills the stock list. */
async function mock(page: Page, permissions: string[]) {
  const posted: Body[] = []
  const stock: Body[] = []
  const routes: Record<string, (body: Body) => unknown> = {
    'GET /api/v1/outlets': () => [
      {
        id: 'o1',
        name: 'Dapur Pusat',
        type: 'central_kitchen',
        timezone: 'Asia/Jakarta',
        is_active: true,
      },
    ],
    'GET /api/v1/catalog/units': () => units,
    'GET /api/v1/catalog/items': () => ({ items: [rice], next_cursor: null }),
    'GET /api/v1/inventory/stock': () => ({ items: stock, next_cursor: null }),
    'POST /api/v1/inventory/opening': (body) => {
      posted.push(body)
      stock.push({
        item_id: 'i-rice',
        sku: 'RICE',
        name: 'Rice',
        unit_code: 'g',
        qty: '25000.0000',
        avg_cost: '12.000000',
        value: 300000,
      })
      return { doc_type: 'opening_balance', doc_id: 'd1', movements: 1 }
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
        permissions,
        all_outlets: true,
        outlet_ids: [],
        modules: ['inventory'],
        subscription: { state: 'active', days_left: null },
        nav: ['inventory'],
        currency: 'IDR',
        language: 'id',
      })
    const handler = routes[`${req.method()} ${path}`]
    const body = (req.postDataJSON() ?? {}) as Body
    return handler ? json(handler(body)) : json({ code: 'not_found' }, 404)
  })
  return posted
}

test('storekeeper posts opening stock and sees it on hand (FR-INV-001, 003)', async ({ page }) => {
  const posted = await mock(page, [
    'inventory.stock.view',
    'inventory.opening.post',
    'catalog.item.view',
    'catalog.cost.view',
  ])
  await page.goto('/inventory')
  await page.getByRole('button', { name: 'EN' }).click()
  await expect(page.getByText('No stock recorded at this outlet yet.')).toBeVisible()

  await page.getByRole('tab', { name: 'Opening stock' }).click()
  await page.getByLabel('Stock date').fill('2026-01-01')
  await page.getByLabel('Add item').fill('rice')
  await page.getByRole('button', { name: /Rice \(RICE\)/ }).click()
  await page.getByLabel('Quantity').fill('25')
  await page.getByRole('combobox', { name: 'Unit', exact: true }).selectOption({ label: 'kg' })
  await page.getByLabel('Cost per unit (IDR)').fill('12.000')
  await page.getByRole('button', { name: 'Post opening stock' }).click()
  await expect(page.getByRole('status').filter({ hasText: 'Posted' })).toBeVisible()
  expect(posted[0]).toEqual({
    outlet_id: 'o1',
    business_date: '2026-01-01',
    lines: [
      {
        item_id: 'i-rice',
        qty: '25',
        unit_id: 'u-kg',
        unit_cost: '12000',
        lot_code: null,
        expiry_date: null,
      },
    ],
  })

  await page.getByRole('tab', { name: 'On hand' }).click()
  await expect(page.getByText('Rice', { exact: true })).toBeVisible()
  await expect(page.getByText(/25[.,]000 g/)).toBeVisible()
})

test('staff without posting rights only see what is on hand', async ({ page }) => {
  await mock(page, ['inventory.stock.view'])
  await page.goto('/inventory')
  await page.getByRole('button', { name: 'EN' }).click()
  await expect(page.getByRole('tab', { name: 'On hand' })).toBeVisible()
  await expect(page.getByRole('tab', { name: 'Opening stock' })).toHaveCount(0)
  await expect(page.getByRole('tab', { name: 'Valuation' })).toHaveCount(0)
})
