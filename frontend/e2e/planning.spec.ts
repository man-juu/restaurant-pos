import { expect, type Page, test } from '@playwright/test'

type Body = Record<string, unknown>

async function mock(page: Page) {
  const calls: { method: string; path: string; body: Body }[] = []
  const routes: Record<string, () => unknown> = {
    'GET /api/v1/outlets': () => [
      {
        id: 'o1',
        name: 'Kitchen',
        type: 'central_kitchen',
        timezone: 'Asia/Jakarta',
        is_active: true,
      },
    ],
    'GET /api/v1/production': () => [],
    'GET /api/v1/production/plan': () => ({
      days: 3,
      rows: [
        {
          item_id: 'i-sambal',
          sku: 'SAMBAL',
          name: 'Sambal',
          unit_code: 'g',
          par_qty: '2000',
          on_hand: '500',
          requested: '1000',
          forecast_use: '600',
          planned: '0',
          suggested: '3100',
          can_make: '2000',
        },
      ],
    }),
    'POST /api/v1/production/plan/accept': () => [],
    'GET /api/v1/inventory/stock': () => ({ items: [], next_cursor: null }),
    'GET /api/v1/inventory/forecast': () => [
      {
        item_id: 'i-rice',
        name: 'Rice',
        unit_code: 'g',
        enough_history: true,
        trend: '1.10',
        daily: '1200',
        days: ['1000', '1000', '1000', '1000', '1500', '1700', '1200'],
        on_hand: '5000',
        eoq: '25000',
      },
    ],
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
        permissions: ['production.order.view', 'production.order.manage', 'inventory.stock.view'],
        all_outlets: true,
        outlet_ids: [],
        modules: ['production', 'inventory'],
        subscription: { state: 'active', days_left: null },
        nav: ['production', 'inventory'],
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

test('kitchen accepts the suggested production plan (FR-PRD-005)', async ({ page }) => {
  const calls = await mock(page)
  await page.goto('/production')
  await page.getByRole('button', { name: 'EN', exact: true }).click()
  await page.getByRole('tab', { name: 'Suggested' }).click()
  await expect(page.getByText(/Ingredients on hand allow only 2[.,]000 g/)).toBeVisible()
  await page.getByLabel('Make (g)').fill('2000')
  await page.getByRole('button', { name: 'Plan 1 order' }).click()
  await expect
    .poll(() => calls.at(-1)?.body)
    .toMatchObject({ outlet_id: 'o1', lines: [{ item_id: 'i-sambal', qty: '2000' }] })
})

test('the forecast shows next week and the order quantity (FR-INV-018)', async ({ page }) => {
  await mock(page)
  await page.goto('/inventory')
  await page.getByRole('button', { name: 'EN', exact: true }).click()
  await page.getByRole('tab', { name: 'Forecast' }).click()
  await expect(page.getByText(/next week 8[.,]400 g/)).toBeVisible()
  await expect(page.getByText(/trend 10 %/)).toBeVisible()
  await expect(page.getByText(/Order quantity: 25[.,]000 g/)).toBeVisible()
})
