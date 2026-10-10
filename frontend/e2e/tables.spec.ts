import { expect, type Route, test } from '@playwright/test'

type Body = Record<string, unknown>

const table = (id: string, name: string, session: Body | null = null) => ({
  id,
  outlet_id: 'o1',
  floor_id: 'f1',
  name,
  capacity: 4,
  x: 0,
  y: 0,
  status: session ? 'occupied' : 'available',
  is_active: true,
  session,
})

test('waiter seats a party and the table shows guests and open amount (FR-TBL-002, 004)', async ({
  page,
}) => {
  let seated: Body | null = null
  const posts: { path: string; body: Body }[] = []
  await page.route('**/api/v1/**', async (route: Route) => {
    const req = route.request()
    const path = new URL(req.url()).pathname
    const json = (data: unknown) => route.fulfill({ json: data })
    if (req.method() !== 'GET') posts.push({ path, body: (req.postDataJSON() ?? {}) as Body })
    const table_: Record<string, () => unknown> = {
      'GET /api/v1/auth/session': () => ({
        user: { id: 'u', email: 'w@x', name: 'Ani', locale: 'en' },
        tenants: [{ id: 't', name: 'Dapur' }],
        active_tenant_id: 't',
        csrf_token: 'c',
        mfa_state: 'ok',
      }),
      'GET /api/v1/me/capabilities': () => ({
        tenant_id: 't',
        permissions: ['tables.table.view', 'tables.session.manage', 'sales.order.create'],
        all_outlets: true,
        outlet_ids: [],
        modules: ['sales', 'tables'],
        subscription: { state: 'active', days_left: null },
        nav: ['pos', 'tables'],
        currency: 'IDR',
        language: 'id',
      }),
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
      'GET /api/v1/tables/floors': () => [
        { id: 'f1', outlet_id: 'o1', name: 'Main', sort_order: 0, is_active: true },
      ],
      'GET /api/v1/tables': () => [table('t1', 'T1', seated), table('t2', 'T2')],
      'POST /api/v1/tables/t1/seat': () => {
        seated = {
          id: 's1',
          status: 'open',
          party_size: 3,
          opened_at: new Date().toISOString(),
          channel_id: 'c1',
          table_ids: ['t1'],
          orders: [
            { id: 'ord1', number: 'POS-2026-000002', status: 'open', subtotal: 0, lines: 0 },
          ],
          open_amount: 0,
        }
        return seated
      },
    }
    const data = table_[`${req.method()} ${path}`]?.()
    return data === undefined
      ? route.fulfill({ status: 404, json: { code: 'not_found' } })
      : json(data)
  })
  await page.goto('/tables')
  await page.getByRole('button', { name: 'EN' }).click()
  await page.getByRole('button', { name: /T1/ }).click()
  await page.getByLabel('Guests').fill('3')
  await page.getByRole('button', { name: 'Seat guests' }).click()
  await expect(page.getByText('3 guests · 0 min')).toBeVisible()
  await expect(page.getByRole('link', { name: 'Open on till' })).toHaveAttribute(
    'href',
    '/pos?order=ord1',
  )
  expect(posts.at(-1)).toEqual({
    path: '/api/v1/tables/t1/seat',
    body: { channel_id: 'c1', party_size: 3 },
  })
})
