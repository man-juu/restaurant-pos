import { expect, type Page, test } from '@playwright/test'

type Body = Record<string, unknown>

const units = [{ id: 'u-kg', code: 'kg', name: 'kilogram', dimension: 'mass', is_platform: true }]
const rice = {
  id: 'i-rice',
  sku: 'RICE',
  type: 'ingredient',
  name: 'Rice',
  category_id: null,
  base_unit_id: 'u-kg',
  is_active: true,
}

/** Fake purchasing API: a quick purchase shows up in "Received". */
async function mock(page: Page, permissions: string[]) {
  const sent: { body: Body; key: string | undefined }[] = []
  const receipts: Body[] = []
  const routes: Record<string, (body: Body) => unknown> = {
    'GET /api/v1/outlets': () => [
      { id: 'o1', name: 'Dapur', type: 'cloud_kitchen', timezone: 'Asia/Jakarta', is_active: true },
    ],
    'GET /api/v1/catalog/units': () => units,
    'GET /api/v1/catalog/items': () => ({ items: [rice], next_cursor: null }),
    'GET /api/v1/purchasing/vendors': () => [],
    'GET /api/v1/purchasing/receipts': () => receipts,
    'POST /api/v1/purchasing/quick-purchases': (body) => {
      const receipt = {
        id: 'r1',
        number: 'GR-2026-00001',
        outlet_id: 'o1',
        vendor_id: null,
        vendor_name: body.vendor_name,
        po_id: null,
        business_date: body.business_date,
        status: 'posted',
        total: 140000,
        invoice_upload_id: null,
        note: null,
        lines: [],
      }
      receipts.push(receipt)
      return receipt
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
        modules: ['inventory', 'purchasing'],
        subscription: { state: 'active', days_left: null },
        nav: ['purchasing'],
        currency: 'IDR',
        language: 'id',
      })
    const handler = routes[`${req.method()} ${path}`]
    const body = (req.postDataJSON() ?? {}) as Body
    if (req.method() === 'POST') sent.push({ body, key: req.headers()['idempotency-key'] })
    return handler ? json(handler(body), req.method() === 'POST' ? 201 : 200) : json({}, 404)
  })
  return sent
}

const BUYER = ['purchasing.vendor.view', 'purchasing.receipt.create', 'catalog.item.view']

test('market purchase is saved once and shows in Received (FR-PUR-004)', async ({ page }) => {
  const sent = await mock(page, BUYER)
  await page.goto('/purchasing')
  await page.getByRole('button', { name: 'EN' }).click()
  await page.getByLabel('Bought where (optional)').fill('Pasar Senen')
  await page.getByLabel('Add an item bought').fill('ri')
  await page.getByRole('button', { name: /Rice/ }).click()
  const save = page.getByRole('button', { name: 'Save purchase' })
  await expect(save).toBeDisabled() // no quantity or price yet
  await page.getByLabel('Quantity').fill('10')
  await page.getByLabel('Paid for this line (IDR)').fill('140.000')
  await expect(page.getByText(/Total .*140[.,]000/)).toBeVisible()
  await save.click()
  await expect(page.getByText('Saved as GR-2026-00001.')).toBeVisible()
  expect(sent).toHaveLength(1)
  expect(sent[0].key).toBeTruthy() // idempotency key: a retry cannot buy twice
  expect(sent[0].body.lines).toEqual([
    { item_id: 'i-rice', qty: '10', unit_id: 'u-kg', line_total: 140000, expiry_date: null },
  ])
  await page.getByRole('tab', { name: 'Received' }).click()
  await expect(page.getByText('GR-2026-00001 · Pasar Senen')).toBeVisible()
})
