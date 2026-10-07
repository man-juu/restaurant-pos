import { expect, type Page, test } from '@playwright/test'

type Body = Record<string, unknown>

const units = [
  { id: 'u-g', code: 'g', name: 'gram', dimension: 'mass', is_platform: true },
  { id: 'u-pcs', code: 'pcs', name: 'piece', dimension: 'count', is_platform: true },
]
const summary = (id: string, name: string, type: string, base: string) => ({
  id,
  sku: name.toUpperCase(),
  type,
  name,
  category_id: null,
  base_unit_id: base,
  is_active: true,
})
const nasi = {
  ...summary('i1', 'Nasi goreng', 'menu', 'u-pcs'),
  is_stocked: false,
  shelf_life_days: null,
  storage_type: null,
  allergens: [],
  version: 1,
  translations: [{ language: 'en', name: 'Nasi goreng', description: null }],
  conversions: [],
}

/** Fake recipe API: one menu item, one ingredient, drafts and activation. */
function fakeRecipes() {
  const state = { boms: [] as Body[], calls: [] as { method: string; path: string; body: Body }[] }
  const bomOut = (b: Body) => ({
    ...b,
    lines: (b.lines as Body[]).map((ln) => ({
      ...ln,
      component_name: 'Rice',
      component_sku: 'RICE',
      qty: String(ln.qty),
      waste_pct: String(ln.waste_pct),
    })),
  })
  const routes: Record<string, (body: Body) => unknown> = {
    'GET /api/v1/catalog/units': () => units,
    'GET /api/v1/catalog/categories': () => [],
    'GET /api/v1/catalog/channels': () => [],
    'GET /api/v1/catalog/items/i1': () => nasi,
    'GET /api/v1/catalog/items/i1/prices': () => [],
    'GET /api/v1/catalog/items': () => ({
      items: [
        summary('i1', 'Nasi goreng', 'menu', 'u-pcs'),
        summary('i2', 'Rice', 'ingredient', 'u-g'),
      ],
      next_cursor: null,
    }),
    'GET /api/v1/catalog/items/i1/boms': () =>
      state.boms.map((b) => Object.fromEntries(Object.entries(b).filter(([k]) => k !== 'lines'))),
    'GET /api/v1/catalog/items/i1/costing': () => ({
      item_id: 'i1',
      on: '2026-10-07',
      bom_id: null,
      lines: [],
      cost: null,
      missing_costs: [],
      cost_visible: true,
      margins: [],
    }),
    'POST /api/v1/catalog/items/i1/boms': (body) => {
      const bom = {
        id: 'b1',
        item_id: 'i1',
        version: 1,
        status: 'draft',
        valid_from: null,
        valid_to: null,
        yield_qty: '1',
        yield_unit_id: 'u-pcs',
        ...body,
      }
      state.boms.push(bom)
      return bomOut(bom)
    },
    'GET /api/v1/catalog/boms/b1': () => bomOut(state.boms[0]),
    'POST /api/v1/catalog/boms/b1/activate': (body) => {
      Object.assign(state.boms[0], { status: 'active', ...body })
      return state.boms[0]
    },
  }
  return { state, routes }
}

async function mock(page: Page) {
  const fake = fakeRecipes()
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
        permissions: ['catalog.item.view', 'catalog.item.update', 'catalog.cost.view'],
        all_outlets: true,
        outlet_ids: [],
        modules: ['catalog'],
        subscription: { state: 'active', days_left: null },
        nav: ['catalog'],
        currency: 'IDR',
        language: 'id',
      })
    const body = (req.postDataJSON() ?? {}) as Body
    if (req.method() !== 'GET') fake.state.calls.push({ method: req.method(), path, body })
    const handler = fake.routes[`${req.method()} ${path}`]
    return handler ? json(handler(body)) : json({ code: 'not_found' }, 404)
  })
  return fake.state
}

test('manager writes a recipe draft and activates it from a date (FR-CAT-005, 006)', async ({
  page,
}) => {
  const state = await mock(page)
  await page.goto('/catalog')
  await page.getByRole('button', { name: 'EN' }).click()
  await page.getByRole('button', { name: /Nasi goreng/ }).click()
  await expect(page.getByText('No active recipe today.')).toBeVisible()

  await page.getByRole('button', { name: 'New recipe version' }).click()
  await page.getByLabel('Add ingredient or semi-finished item').fill('rice')
  await page.getByRole('button', { name: /Rice \(RICE\)/ }).click()
  await page.getByLabel('Quantity').fill('200')
  await page.getByLabel('Waste %').fill('5')
  const recipe = page
    .locator('section')
    .filter({ has: page.getByRole('heading', { name: 'Recipe' }) })
  await recipe.getByRole('button', { name: 'Save' }).click()

  await expect(page.getByRole('heading', { name: 'Draft v1' })).toBeVisible()
  await page.getByLabel('Use from').fill('2026-11-01')
  await page.getByRole('button', { name: 'Activate' }).click()
  await expect
    .poll(() => state.calls.map((c) => `${c.method} ${c.path}`))
    .toEqual(['POST /api/v1/catalog/items/i1/boms', 'POST /api/v1/catalog/boms/b1/activate'])
  expect(state.calls[0].body).toEqual({
    lines: [{ component_item_id: 'i2', qty: '200', unit_id: 'u-g', waste_pct: '5' }],
  })
  expect(state.calls[1].body).toEqual({ valid_from: '2026-11-01' })
})
