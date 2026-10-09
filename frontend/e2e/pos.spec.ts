import { expect, type Page, type Route, test } from '@playwright/test'

type Body = Record<string, unknown>

const SESSION = {
  user: { id: 'u', email: 'o@x', name: 'Rina', locale: 'en' },
  tenants: [{ id: 't', name: 'Dapur' }],
  active_tenant_id: 't',
  csrf_token: 'c',
  mfa_state: 'ok',
}

const caps = (permissions: string[]) => ({
  tenant_id: 't',
  permissions,
  all_outlets: true,
  outlet_ids: [],
  modules: ['inventory', 'sales'],
  subscription: { state: 'active', days_left: null },
  nav: ['pos'],
  currency: 'IDR',
  language: 'id',
})

const NASI = {
  id: 'i-nasi',
  name: 'Fried rice',
  sku: 'NASI',
  category_id: null,
  photo_upload_id: null,
  is_available: true,
  price: 25000,
  modifier_groups: [
    {
      id: 'g1',
      name: 'Add-ons',
      min_select: 0,
      max_select: 1,
      is_active: true,
      options: [{ id: 'o-egg', name: 'Extra egg', price_delta: 5000, is_active: true }],
    },
  ],
}

/** A tiny in-memory till server: one order, totals with 10 % tax. */
function fakeTill() {
  const state = {
    shift: null as Body | null,
    order: null as Body | null,
    paid: null as Body | null,
  }
  const lines: Body[] = []
  const order = () => {
    const subtotal = lines.reduce((s, l) => s + (l.line_total as number), 0)
    const tax = Math.round(subtotal / 10)
    return {
      id: 'ord1',
      number: 'POS-2026-000001',
      status: state.paid ? 'paid' : 'open',
      outlet_id: 'o1',
      channel_id: 'c1',
      label: null,
      note: null,
      created_at: '2026-10-09T10:00:00Z',
      paid_at: null,
      lines,
      totals: { subtotal, service_charge: 0, tax, total: subtotal + tax },
      payments: state.paid ? (state.paid.payments as Body[]) : [],
    }
  }
  return { state, lines, order }
}

const shiftOut = (float: number) => ({
  id: 's1',
  outlet_id: 'o1',
  cashier_id: 'u',
  cashier_name: 'Rina',
  status: 'open',
  opening_float: float,
  opened_at: '2026-10-09T08:00:00Z',
  closed_at: null,
  cash_sales: 0,
  cash_in: 0,
  cash_out: 0,
  expected: float,
  counted: null,
  variance: null,
  by_method: {},
  orders: 0,
  note: null,
  movements: [],
})

function routeTill(fake: ReturnType<typeof fakeTill>, method: string, path: string, body: Body) {
  const table: Record<string, () => unknown> = {
    'GET /api/v1/outlets': () => [
      { id: 'o1', name: 'Shop', type: 'branch', timezone: 'Asia/Jakarta', is_active: true },
    ],
    'GET /api/v1/catalog/channels': () => [
      {
        id: 'c1',
        code: 'dine_in',
        name: 'Dine-in',
        kind: 'dine_in',
        platform: null,
        sort_order: 0,
        is_active: true,
      },
    ],
    'GET /api/v1/catalog/categories': () => [],
    'GET /api/v1/catalog/menu': () => [NASI],
    'GET /api/v1/settings': () => ({
      payment_methods: {
        methods: [
          { code: 'cash', name: 'Cash', kind: 'cash', active: true },
          { code: 'qris', name: 'QRIS', kind: 'qris_static', active: true },
        ],
      },
      pos: { require_shift: true, cash_rounding_step: 0, tips_enabled: false },
    }),
    'GET /api/v1/pos/shifts/current': () => fake.state.shift,
    'POST /api/v1/pos/shifts': () => (fake.state.shift = shiftOut(body.opening_float as number)),
    'GET /api/v1/pos/orders': () => [],
    'POST /api/v1/pos/orders': () => fake.order(),
    'GET /api/v1/pos/orders/ord1': () => fake.order(),
    'POST /api/v1/pos/orders/ord1/lines': () => {
      const extra = (body.option_ids as string[]).length ? 5000 : 0
      fake.lines.push({
        id: `l${fake.lines.length}`,
        item_id: 'i-nasi',
        name: 'Fried rice',
        qty: '1',
        unit_price: 25000 + extra,
        modifiers: extra ? [{ option_id: 'o-egg', name: 'Extra egg', price_delta: 5000 }] : [],
        line_total: 25000 + extra,
        note: body.note,
        status: 'new',
      })
      return fake.order()
    },
    'POST /api/v1/pos/orders/ord1/pay': () => {
      fake.state.paid = {
        payments: (body.payments as Body[]).map((p) => ({
          ...p,
          kind: 'cash',
          change: (p.tendered as number) - (p.amount as number),
          reference: null,
        })),
      }
      return fake.order()
    },
  }
  return table[`${method} ${path}`]?.()
}

async function mock(page: Page, permissions: string[]) {
  const fake = fakeTill()
  const posts: { path: string; body: Body }[] = []
  await page.route('**/api/v1/**', async (route: Route) => {
    const req = route.request()
    const path = new URL(req.url()).pathname
    if (path === '/api/v1/auth/session') return route.fulfill({ json: SESSION })
    if (path === '/api/v1/me/capabilities') return route.fulfill({ json: caps(permissions) })
    const body = (req.postDataJSON() ?? {}) as Body
    if (req.method() !== 'GET') posts.push({ path, body })
    const data = routeTill(fake, req.method(), path, body)
    return data === undefined
      ? route.fulfill({ status: 404, json: { code: 'not_found' } })
      : route.fulfill({ json: data })
  })
  return posts
}

const CASHIER = [
  'sales.order.create',
  'sales.order.pay',
  'sales.shift.open',
  'catalog.item.view',
  'tenant.settings.view',
]

test('cashier opens a shift, sells with a modifier and gives change (FR-SAL-004 to 006, 009)', async ({
  page,
}) => {
  const posts = await mock(page, CASHIER)
  await page.goto('/pos')
  await page.getByRole('button', { name: 'EN' }).click()
  await page.getByLabel('Opening cash').fill('100.000')
  await page.getByRole('button', { name: 'Open shift' }).click()

  await page.getByRole('button', { name: /Fried rice/ }).click()
  await page.getByRole('checkbox', { name: /Extra egg/ }).check()
  await page.getByRole('button', { name: 'Add to order' }).click()
  await expect(page.getByText('Extra egg')).toBeVisible()
  await expect(page.getByText(/33[.,]000/).first()).toBeVisible() // 30.000 + 10 % tax

  await page.getByRole('button', { name: 'Pay', exact: true }).click()
  await page.getByRole('button', { name: /50[.,]000/ }).click()
  await expect(page.getByRole('status').getByText(/Change: .*17[.,]000/)).toBeVisible()
  await page.getByRole('button', { name: 'Confirm payment' }).click()
  await expect(page.getByText('POS-2026-000001 paid')).toBeVisible()
  expect(posts.find((p) => p.path.endsWith('/pay'))?.body).toEqual({
    tip: 0,
    payments: [{ method: 'cash', amount: 33000, tendered: 50000 }],
  })
})

test('a waiter takes orders but sees no pay button', async ({ page }) => {
  await mock(page, ['sales.order.create', 'catalog.item.view'])
  await page.goto('/pos')
  await page.getByRole('button', { name: 'EN' }).click()
  await page.getByRole('button', { name: /Fried rice/ }).click()
  await page.getByRole('button', { name: 'Add to order' }).click()
  await expect(page.getByRole('button', { name: 'Send to kitchen' })).toBeEnabled()
  await expect(page.getByRole('button', { name: 'Pay', exact: true })).toHaveCount(0)
})
