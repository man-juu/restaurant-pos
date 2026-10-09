import { expect, type Route, test } from '@playwright/test'

const ticket = {
  id: 'k1',
  station_id: null,
  order_id: 'ord1',
  order_number: 'POS-2026-000003',
  label: 'Table 4',
  channel_name: 'GoFood',
  platform: 'gofood',
  status: 'new',
  created_at: new Date(Date.now() - 20 * 60_000).toISOString(),
  ready_at: null,
  bumped_at: null,
  late: true,
  items: [
    {
      id: 'i1',
      name: 'Fried rice',
      qty: '2.0000',
      modifiers: 'Extra egg',
      note: 'no onion',
      status: 'active',
    },
  ],
}

test('cook sees a late delivery ticket and starts it (FR-KDS-001, 003, 004)', async ({ page }) => {
  const posts: string[] = []
  await page.route('**/api/v1/**', async (route: Route) => {
    const req = route.request()
    const path = new URL(req.url()).pathname
    if (req.method() !== 'GET') {
      posts.push(path)
      return route.fulfill({ status: 204 })
    }
    const data: Record<string, unknown> = {
      '/api/v1/auth/session': {
        user: { id: 'u', email: 'k@x', name: 'Budi', locale: 'en' },
        tenants: [{ id: 't', name: 'Dapur' }],
        active_tenant_id: 't',
        csrf_token: 'c',
        mfa_state: 'ok',
      },
      '/api/v1/me/capabilities': {
        tenant_id: 't',
        permissions: ['kitchen.ticket.view', 'kitchen.ticket.update'],
        all_outlets: false,
        outlet_ids: ['o1'],
        modules: ['sales', 'kitchen'],
        subscription: { state: 'active', days_left: null },
        nav: ['kitchen'],
        currency: 'IDR',
        language: 'id',
      },
      '/api/v1/outlets': [
        { id: 'o1', name: 'Shop', type: 'branch', timezone: 'Asia/Jakarta', is_active: true },
      ],
      '/api/v1/kitchen/stations': [],
      '/api/v1/kitchen/tickets': [ticket],
    }
    return path in data
      ? route.fulfill({ json: data[path] })
      : route.fulfill({ status: 404, json: { code: 'not_found' } })
  })
  await page.goto('/kitchen')
  await page.getByRole('button', { name: 'EN' }).click()
  const card = page.getByRole('region', { name: 'New' }).getByRole('article')
  await expect(card.getByText('Table 4')).toBeVisible()
  await expect(card.getByText('gofood')).toBeVisible()
  await expect(card.getByText('no onion')).toBeVisible()
  await expect(card.getByText('20 min')).toBeVisible()
  await card.getByRole('button', { name: 'Start' }).click()
  await expect.poll(() => posts.at(-1)).toBe('/api/v1/kitchen/tickets/k1/start')
})
