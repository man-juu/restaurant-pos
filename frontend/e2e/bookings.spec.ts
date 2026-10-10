import { expect, type Route, test } from '@playwright/test'

type Body = Record<string, unknown>

const caps = {
  tenant_id: 't',
  permissions: ['tables.table.view', 'tables.session.manage', 'tenant.customer.view'],
  all_outlets: true,
  outlet_ids: [],
  modules: ['sales', 'tables'],
  subscription: { state: 'active', days_left: null },
  nav: ['tables'],
  currency: 'IDR',
  language: 'id',
}

const booked = {
  id: 'r1',
  outlet_id: 'o1',
  customer_id: 'c9',
  guest_name: 'Sari',
  guest_phone: '628111',
  no_shows: 1,
  party_size: 4,
  starts_at: '2030-01-01T12:00:00Z',
  duration_min: 90,
  status: 'pending',
  notes: null,
  table_ids: ['t2'],
  session_id: null,
}

test('book a table from the suggestions; the list warns about past no-shows (FR-TBL-005 to 007)', async ({
  page,
}) => {
  const posts: { path: string; body: Body }[] = []
  let list: Body[] = []
  await page.route('**/api/v1/**', async (route: Route) => {
    const req = route.request()
    const path = new URL(req.url()).pathname
    if (req.method() !== 'GET') posts.push({ path, body: (req.postDataJSON() ?? {}) as Body })
    const routes: Record<string, () => unknown> = {
      'GET /api/v1/auth/session': () => ({
        user: { id: 'u', email: 'w@x', name: 'Ani', locale: 'en' },
        tenants: [{ id: 't', name: 'Dapur' }],
        active_tenant_id: 't',
        csrf_token: 'c',
        mfa_state: 'ok',
      }),
      'GET /api/v1/me/capabilities': () => caps,
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
      'GET /api/v1/tables': () => [
        {
          id: 't2',
          outlet_id: 'o1',
          floor_id: 'f1',
          name: 'T2',
          capacity: 4,
          x: 0,
          y: 0,
          status: 'available',
          is_active: true,
          session: null,
        },
      ],
      'GET /api/v1/bookings/suggest': () => [{ table_ids: ['t2'], names: ['T2'], capacity: 4 }],
      'GET /api/v1/bookings/reservations': () => list,
      'POST /api/v1/bookings/reservations': () => {
        list = [booked]
        return booked
      },
    }
    const data = routes[`${req.method()} ${path}`]?.()
    return data === undefined
      ? route.fulfill({ status: 404, json: { code: 'not_found' } })
      : route.fulfill({ json: data })
  })
  await page.goto('/tables')
  await page.getByRole('button', { name: 'EN', exact: true }).click()
  await page.getByRole('tab', { name: 'Reservations' }).click()
  await page.getByRole('button', { name: 'New reservation' }).click()
  await page.getByLabel('Guest name').fill('Sari')
  await page.getByLabel('Phone').fill('08111')
  await page.getByLabel('Guests').fill('4')
  await page.getByRole('button', { name: 'T2 (4 seats)' }).click()
  await page.getByRole('button', { name: 'Save reservation' }).click()
  await expect
    .poll(() => posts.at(-1)?.body)
    .toMatchObject({
      guest: { name: 'Sari', phone: '08111' },
      party_size: 4,
      table_ids: ['t2'],
    })
  await expect(page.getByText('Did not come 1 time before')).toBeVisible()
})
