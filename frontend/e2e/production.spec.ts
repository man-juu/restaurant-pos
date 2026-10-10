import { expect, type Page, test } from '@playwright/test'

type Body = Record<string, unknown>

const sambal = {
  id: 'i-sambal',
  sku: 'SAMBAL',
  type: 'semi_finished',
  name: 'Sambal',
  category_id: null,
  base_unit_id: 'u-g',
  is_active: true,
}

const today = new Date().toISOString().slice(0, 10)

function planned(body: Body): Body {
  return {
    id: 'p1',
    number: 'PRD-2026-00001',
    outlet_id: 'o1',
    item_id: 'i-sambal',
    item_name: 'Sambal',
    unit_code: 'g',
    bom_id: 'b1',
    production_date: body.production_date,
    status: 'planned',
    planned_qty: body.planned_qty,
    actual_qty: null,
    yield_variance: null,
    input_value: 0,
    unit_cost: null,
    expiry_date: null,
    lot_code: null,
    note: null,
    created_at: '2026-10-08T00:00:00Z',
    completed_at: null,
    lines: [
      {
        id: 'l1',
        item_id: 'i-chili',
        item_name: 'Chili',
        unit_code: 'g',
        planned_qty: '1000.0000',
        actual_qty: null,
        value: 0,
      },
    ],
  }
}

/** Fake production API: plan, then complete; the card shows the result. */
async function mock(page: Page) {
  const sent: { path: string; body: Body; key?: string }[] = []
  let orders: Body[] = []
  const routes: Record<string, (body: Body) => unknown> = {
    'GET /api/v1/outlets': () => [
      {
        id: 'o1',
        name: 'Dapur',
        type: 'central_kitchen',
        timezone: 'Asia/Jakarta',
        is_active: true,
      },
    ],
    'GET /api/v1/catalog/items': () => ({ items: [sambal], next_cursor: null }),
    'GET /api/v1/production/orders': () => orders,
    'GET /api/v1/production/prep-list': () => [
      {
        item_id: 'i-sambal',
        sku: 'SAMBAL',
        name: 'Sambal',
        unit_code: 'g',
        par_qty: '2000.0000',
        on_hand: '500.0000',
        requested: '200',
        planned: '0',
        suggested: '1700.0000',
      },
    ],
    'POST /api/v1/production/orders': (body) => {
      orders = [planned(body)]
      return orders[0]
    },
    'POST /api/v1/production/orders/p1/complete': (body) => {
      orders = [
        {
          ...orders[0],
          status: 'completed',
          actual_qty: body.actual_qty,
          yield_variance: '-100',
          input_value: 35000,
          expiry_date: '2026-10-11',
        },
      ]
      return orders[0]
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
        permissions: ['production.order.view', 'production.order.manage', 'catalog.item.view'],
        all_outlets: true,
        outlet_ids: [],
        modules: ['inventory', 'production'],
        subscription: { state: 'active', days_left: null },
        nav: ['production'],
        currency: 'IDR',
        language: 'id',
      })
    const handler = routes[`${req.method()} ${path}`]
    const body = (req.postDataJSON() ?? {}) as Body
    if (req.method() === 'POST') sent.push({ path, body, key: req.headers()['idempotency-key'] })
    return handler ? json(handler(body)) : json({}, 404)
  })
  return sent
}

test('cook plans sambal, records a smaller yield and sees cost and use-by (FR-PRD-001 to 004)', async ({
  page,
}) => {
  const sent = await mock(page)
  await page.goto('/production')
  await page.getByRole('button', { name: 'EN' }).click()
  await page.getByLabel('What to make (semi-finished item)').fill('sam')
  await page.getByRole('button', { name: /Sambal/ }).click()
  await page.getByLabel('Quantity to make (base unit)').fill('1000')
  await page.getByRole('button', { name: 'Add to plan' }).click()
  await expect(page.getByText('PRD-2026-00001 · Sambal')).toBeVisible()
  expect(sent[0].key).toBeTruthy()
  expect(sent[0].body).toEqual({
    outlet_id: 'o1',
    item_id: 'i-sambal',
    planned_qty: '1000',
    production_date: today,
  })
  await page.getByLabel('Quantity made (g)').fill('900')
  await page.getByRole('button', { name: 'Save and post stock' }).click()
  await expect(page.getByText('Difference from plan: -100 g')).toBeVisible()
  await expect(page.getByText(/Ingredients used: .*35[.,]000/)).toBeVisible()
  await expect(page.getByText('Use by 2026-10-11')).toBeVisible()
  expect(sent.at(-1)?.body).toEqual({ actual_qty: '900', used: [], confirm_negative: false })
})

test('prep list shows what is below par, ticks off and plans it (FR-PRD-008)', async ({ page }) => {
  const sent = await mock(page)
  await page.goto('/production')
  await page.getByRole('button', { name: 'EN' }).click()
  await page.getByRole('tab', { name: 'Prep list' }).click()
  await expect(
    page.getByText('Make 1700 g · have 500 · par 2000 · requested 200 · planned 0'),
  ).toBeVisible()
  await expect(page.getByRole('link', { name: 'Print prep list (PDF)' })).toBeVisible()
  const tick = page.getByRole('checkbox', { name: /Sambal/ })
  await tick.check()
  await expect(tick).toBeChecked()
  await page.getByRole('button', { name: 'Plan it' }).click()
  await expect.poll(() => sent.at(-1)?.body.planned_qty).toBe('1700.0000')
})
