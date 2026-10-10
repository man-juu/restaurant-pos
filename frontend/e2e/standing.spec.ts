import { expect, test } from '@playwright/test'

type Body = Record<string, unknown>

const outlets = [
  { id: 'shop', name: 'Shop', type: 'branch', timezone: 'Asia/Jakarta', is_active: true },
  {
    id: 'ck',
    name: 'Central kitchen',
    type: 'central_kitchen',
    timezone: 'Asia/Jakarta',
    is_active: true,
  },
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

test('a branch sets up a standing order and makes the due requests (FR-TRF-005)', async ({
  page,
}) => {
  const calls: { method: string; path: string; body: Body }[] = []
  const standing: Body[] = []
  await page.route('**/api/v1/**', async (route) => {
    const req = route.request()
    const path = new URL(req.url()).pathname
    const json = (data: unknown, status = 200) => route.fulfill({ status, json: data })
    if (req.method() !== 'GET')
      calls.push({ method: req.method(), path, body: (req.postDataJSON() ?? {}) as Body })
    const routes: Record<string, () => unknown> = {
      'GET /api/v1/auth/session': () => ({
        user: { id: 'u', email: 'o@x', name: 'Rina', locale: 'en' },
        tenants: [{ id: 't', name: 'Dapur' }],
        active_tenant_id: 't',
        csrf_token: 'c',
        mfa_state: 'ok',
      }),
      'GET /api/v1/me/capabilities': () => ({
        tenant_id: 't',
        permissions: ['transfers.transfer.view', 'transfers.transfer.request'],
        all_outlets: true,
        outlet_ids: [],
        modules: ['transfers'],
        subscription: { state: 'active', days_left: null },
        nav: ['transfers'],
        currency: 'IDR',
        language: 'id',
      }),
      'GET /api/v1/outlets': () => outlets,
      'GET /api/v1/transfers': () => [],
      'GET /api/v1/catalog/items': () => ({ items: [rice], next_cursor: null }),
      'GET /api/v1/transfers/standing': () => standing,
      'POST /api/v1/transfers/standing': () => {
        const made = {
          id: 's1',
          from_outlet_id: 'ck',
          to_outlet_id: 'shop',
          weekdays: [0, 3],
          lead_days: 1,
          is_active: true,
          note: null,
          lines: [{ item_id: 'i-rice', qty: '2000', name: 'Rice', unit_code: 'g' }],
          next_delivery: '2026-10-12',
        }
        standing.push(made)
        return made
      },
      'POST /api/v1/transfers/standing/run': () => ({ made: 1 }),
    }
    const handler = routes[`${req.method()} ${path}`]
    return handler ? json(handler()) : json({ code: 'not_found' }, 404)
  })
  await page.goto('/transfers')
  await page.getByRole('button', { name: 'EN', exact: true }).click()
  await page.getByRole('tab', { name: 'Standing orders' }).click()
  await expect(page.getByRole('tab', { name: 'Charges' })).toHaveCount(0) // no cost view
  await page.getByRole('button', { name: 'New standing order' }).click()
  await page.getByLabel('Monday').check()
  await page.getByLabel('Thursday').check()
  await page.getByLabel('Add an item').fill('rice')
  await page.getByRole('button', { name: /Rice \(RICE\)/ }).click()
  await page.getByLabel('Rice (base unit)').fill('2000')
  await page.getByRole('button', { name: 'Save standing order' }).click()
  await expect(page.getByText(/Monday, Thursday/)).toBeVisible()
  expect(calls.at(-1)?.body).toMatchObject({
    from_outlet_id: 'ck',
    to_outlet_id: 'shop',
    weekdays: [0, 3],
    lines: [{ item_id: 'i-rice', qty: '2000' }],
  })
  await page.getByRole('button', { name: 'Make due requests now' }).click()
  await expect(page.getByText('1 request made.')).toBeVisible()
})
