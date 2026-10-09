import { expect, type Page, type Route, test } from '@playwright/test'

/** In-memory stand-in for the catalog API, enough to walk through the screens. */
function fakeCatalog() {
  const units = [
    { id: 'u-g', code: 'g', name: 'gram', dimension: 'mass', is_platform: true },
    { id: 'u-pcs', code: 'pcs', name: 'piece', dimension: 'count', is_platform: true },
  ]
  const channels: Record<string, unknown>[] = []
  const items: Record<string, unknown>[] = []
  const prices: Record<string, unknown>[] = []
  const groups: Record<string, unknown>[] = []
  const posts: { path: string; body: Record<string, unknown> }[] = []
  return { units, channels, items, prices, groups, posts }
}

type Fake = ReturnType<typeof fakeCatalog>

type Body = Record<string, unknown>

function newItem(fake: Fake, body: Body) {
  const translations = body.translations as { language: string; name: string }[]
  const row = {
    ...body,
    id: 'i1',
    name: translations[0].name,
    is_active: true,
    version: 1,
    translations: translations.map((t) => ({ description: null, ...t })),
  }
  fake.items.push(row)
  return row
}

const add = (list: Body[], row: Body) => {
  list.push(row)
  return row
}

const usage = (remaining: number) => ({
  enabled: true,
  tenant_used: 2 - remaining,
  tenant_limit: 2,
  remaining,
  resets_at: '2026-10-09T00:00:00Z',
})

/** "METHOD path" -> handler; a lookup table instead of an if-chain. */
const ROUTES: Record<string, (fake: Fake, body: Body) => unknown> = {
  'GET /api/v1/catalog/units': (f) => f.units,
  'GET /api/v1/catalog/categories': () => [],
  'GET /api/v1/catalog/channels': (f) => f.channels,
  'POST /api/v1/catalog/channels': (f, b) =>
    add(f.channels, { id: `c${f.channels.length}`, sort_order: 0, is_active: true, ...b }),
  'GET /api/v1/catalog/items': (f) => ({ items: f.items, next_cursor: null }),
  'POST /api/v1/catalog/items': newItem,
  'GET /api/v1/catalog/items/i1': (f) => f.items[0],
  'GET /api/v1/catalog/items/i1/prices': (f) => f.prices,
  'PUT /api/v1/catalog/items/i1/photo': (f) => {
    f.items[0].photo_upload_id = 'up1'
    return { id: 'up1', content_type: 'image/webp', width: 1, height: 1, byte_size: 68 }
  },
  'GET /api/v1/catalog/modifier-groups': (f) => f.groups,
  'POST /api/v1/catalog/modifier-groups': (f, b) => {
    const options = (b.options as Body[]).map((o, i) => ({ ...o, id: `o${i}` }))
    return add(f.groups, { ...b, id: `g${f.groups.length}`, options })
  },
  'GET /api/v1/catalog/imports': () => [],
  'POST /api/v1/catalog/imports/items/check': () => ({
    rows_ok: 1,
    errors: [{ row: 3, field: 'base_unit' }],
  }),
  'GET /api/v1/catalog/ai-images/usage': () => usage(2),
  'POST /api/v1/catalog/ai-images': () => ({
    image: { id: 'ai1', content_type: 'image/webp', width: 1, height: 1, byte_size: 68 },
    usage: usage(0),
  }),
  'PUT /api/v1/catalog/items/i1/photo/ai1': (f) => {
    f.items[0].photo_upload_id = 'ai1'
    return { id: 'ai1', content_type: 'image/webp', width: 1, height: 1, byte_size: 68 }
  },
  'PUT /api/v1/catalog/items/i1/prices': (f, b) =>
    add(f.prices, { id: `p${f.prices.length}`, item_id: 'i1', ...b }),
}

function catalogRoute(fake: Fake, path: string, method: string, body: Body) {
  return ROUTES[`${method} ${path}`]?.(fake, body)
}

// 1x1 transparent PNG.
const PNG = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=',
  'base64',
)

function parseBody(raw: string | null, type = ''): Body {
  if (!raw || !type.includes('json')) return {}
  return JSON.parse(raw) as Body
}

async function mock(page: Page, permissions: string[]) {
  const fake = fakeCatalog()
  await page.route('**/api/v1/**', async (route: Route) => {
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
        modules: ['catalog'],
        subscription: { state: 'active', days_left: null },
        nav: ['catalog'],
        currency: 'IDR',
        language: 'id',
      })
    if (path.startsWith('/api/v1/uploads/'))
      return route.fulfill({ status: 200, contentType: 'image/png', body: PNG })
    const body = parseBody(req.postData(), req.headers()['content-type'])
    if (req.method() !== 'GET') fake.posts.push({ path, body })
    const data = catalogRoute(fake, path, req.method(), body)
    return data === undefined ? json({ code: 'not_found' }, 404) : json(data)
  })
  return fake
}

const EDIT = ['catalog.item.view', 'catalog.item.create', 'catalog.item.update']

test('manager adds a channel, an item and its dine-in price (FR-CAT-001, 004)', async ({
  page,
}) => {
  const fake = await mock(page, EDIT)
  await page.goto('/catalog')
  await page.getByRole('button', { name: 'EN' }).click()

  await page.getByRole('tab', { name: 'Sales channels' }).click()
  await page.getByRole('button', { name: 'New channel' }).click()
  await page.getByLabel('Name', { exact: true }).fill('Dine-in')
  await page.getByLabel('Code').fill('dine_in')
  await page.getByRole('button', { name: 'Save' }).click()
  await expect(page.getByText('Dine-in').first()).toBeVisible()

  await page.getByRole('tab', { name: 'Items' }).click()
  await page.getByRole('button', { name: 'New item' }).click()
  const save = page.getByRole('button', { name: 'Save' })
  await expect(save).toBeDisabled() // no name, SKU or unit yet
  await page.getByLabel('Name (English)').fill('Fried rice')
  await page.getByLabel('Name (Indonesian)').fill('Nasi goreng')
  await page.getByLabel('SKU').fill('NASI-01')
  await page.getByRole('combobox', { name: /^Base unit/ }).selectOption({ label: 'pcs (piece)' })
  await save.click()

  await expect(page.getByRole('heading', { name: 'Prices per channel' })).toBeVisible()
  await page.getByLabel('Start date').fill('2026-01-01')
  await page.getByLabel('Price (IDR)').fill('25.000')
  await page.getByRole('button', { name: 'Save' }).last().click()
  await expect(page.getByText(/25[.,]000/).first()).toBeVisible()
  expect(fake.posts.at(-1)).toEqual({
    path: '/api/v1/catalog/items/i1/prices',
    body: { channel_id: 'c0', valid_from: '2026-01-01', price: 25000, outlet_id: null },
  })

  // Optional photo: choose a file, the item now shows it.
  await page.getByLabel('Choose photo').setInputFiles({
    name: 'rice.png',
    mimeType: 'image/png',
    buffer: PNG,
  })
  await expect(page.getByRole('img', { name: 'Photo of Fried rice' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Replace photo' })).toBeVisible()

  // Free AI image: counter shown, generate, accept; at 0 left the button is blocked.
  await expect(page.getByText(/2 images left today/)).toBeVisible()
  await page.getByLabel('Describe the photo').fill('fried rice on a plate')
  await page.getByRole('button', { name: 'Create image' }).click()
  await expect(page.getByText(/0 images left today/)).toBeVisible()
  await expect(page.getByRole('button', { name: 'Create image' })).toBeDisabled()
  await page.getByRole('button', { name: 'Use this photo' }).click()
  // The click only starts the request: wait until the fake API has received it.
  await expect.poll(() => fake.posts.at(-1)?.path).toBe('/api/v1/catalog/items/i1/photo/ai1')
})

test('manager adds a modifier group with a price change (FR-CAT-003)', async ({ page }) => {
  const fake = await mock(page, EDIT)
  await page.goto('/catalog')
  await page.getByRole('button', { name: 'EN' }).click()
  await page.getByRole('tab', { name: 'Modifiers' }).click()
  await page.getByRole('button', { name: 'New modifier group' }).click()
  await page.getByLabel('Group name').fill('Spice level')
  await page.getByLabel('Option', { exact: true }).fill('Extra spicy')
  await page.getByLabel('Price change (can be negative)').fill('2000')
  await page.getByRole('button', { name: 'Save' }).click()
  await expect(page.getByText('Extra spicy')).toBeVisible()
  expect(fake.posts.at(-1)?.body).toMatchObject({
    name: 'Spice level',
    min_select: 0,
    max_select: 1,
    options: [{ name: 'Extra spicy', price_delta: 2000 }],
  })
})

test('staff without edit rights see the catalog read-only', async ({ page }) => {
  await mock(page, ['catalog.item.view'])
  await page.goto('/catalog')
  await page.getByRole('button', { name: 'EN' }).click()
  await expect(page.getByText('Ask a manager to change items or prices.')).toBeVisible()
  await expect(page.getByRole('button', { name: 'New item' })).toHaveCount(0)
})

test('import shows problem rows and blocks the import (FR-IMP-001)', async ({ page }) => {
  const fake = await mock(page, EDIT)
  await page.goto('/catalog')
  await page.getByRole('button', { name: 'EN' }).click()
  await page.getByRole('button', { name: 'Import', exact: true }).click()
  await page.getByLabel(/File \(.xlsx or .csv/).setInputFiles({
    name: 'items.csv',
    mimeType: 'text/csv',
    buffer: Buffer.from('sku,type,base_unit\nA,ingredient,g\nB,ingredient,parsec\n'),
  })
  await expect(page.getByText('Row 3: check base unit')).toBeVisible()
  await expect(page.getByRole('button', { name: /^Import 1 item/ })).toBeDisabled()
  await expect.poll(() => fake.posts.at(-1)?.path).toBe('/api/v1/catalog/imports/items/check')
  await expect(page.getByRole('link', { name: 'Export Excel' })).toBeVisible()
})
