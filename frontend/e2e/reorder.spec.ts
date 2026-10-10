import { expect, type Page, test } from '@playwright/test'

type Body = Record<string, unknown>

const group = {
  vendor_id: 'v1',
  vendor_name: 'CV Beras',
  lines: [
    {
      item_id: 'i-rice',
      name: 'Rice',
      unit_code: 'g',
      on_hand: '10000',
      reorder_point: '12000',
      suggested: '30000',
      order_qty: '50',
      order_unit_id: 'u-kg',
      unit_price: 13600,
    },
  ],
}

async function mock(page: Page) {
  const sent: Body[] = []
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
        permissions: ['purchasing.vendor.view', 'purchasing.order.create'],
        all_outlets: true,
        outlet_ids: [],
        modules: ['inventory', 'purchasing'],
        subscription: { state: 'active', days_left: null },
        nav: ['purchasing'],
        currency: 'IDR',
        language: 'id',
      })
    if (path === '/api/v1/outlets')
      return json([
        { id: 'o1', name: 'Shop', type: 'branch', timezone: 'Asia/Jakarta', is_active: true },
      ])
    if (path === '/api/v1/purchasing/reorder-suggestions') return json([group])
    if (path === '/api/v1/purchasing/orders' && req.method() === 'POST') {
      sent.push(req.postDataJSON() as Body)
      return json({ id: 'po1', status: 'draft' }, 201)
    }
    if (path === '/api/v1/purchasing/orders') return json([])
    return json([], 200)
  })
  return sent
}

test('reorder suggestion becomes a draft purchase order (FR-INV-013)', async ({ page }) => {
  const sent = await mock(page)
  await page.goto('/purchasing')
  await page.getByRole('button', { name: 'EN' }).click()
  await page.getByRole('tab', { name: 'Reorder' }).click()
  await expect(page.getByText('Rice: have 10000 g, reorder at 12000, needs 30000 g')).toBeVisible()
  await page.getByRole('button', { name: 'Make a draft order' }).click()
  await expect.poll(() => sent.length).toBe(1)
  expect(sent[0].lines).toEqual([
    { item_id: 'i-rice', qty: '50', unit_id: 'u-kg', unit_price: 13600 },
  ])
  await expect(page.getByRole('tab', { name: 'Orders', selected: true })).toBeVisible()
})
