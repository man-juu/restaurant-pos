import { expect, type Page, test } from '@playwright/test'

const note = {
  id: 'n1',
  kind: 'below_reorder_point',
  params: { item: 'Rice', qty: '20000', unit: 'g', point: '30000' },
  link: '/inventory',
  created_at: '2026-10-09T01:00:00Z',
  read_at: null as string | null,
}

/** Fake API: one unread stock alert. */
async function mock(page: Page) {
  const reads: string[] = []
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
        permissions: ['inventory.stock.view'],
        all_outlets: true,
        outlet_ids: [],
        modules: ['inventory'],
        subscription: { state: 'active', days_left: null },
        nav: ['inventory'],
        currency: 'IDR',
        language: 'id',
      })
    if (path === '/api/v1/notifications/unread-count') return json({ unread: note.read_at ? 0 : 1 })
    if (path === '/api/v1/notifications') return json([note])
    if (path === '/api/v1/notifications/n1/read') {
      reads.push(path)
      note.read_at = '2026-10-09T01:05:00Z'
      return route.fulfill({ status: 204 })
    }
    return json({}, 404)
  })
  return reads
}

test('bell shows unread alerts; opening one marks it read (FR-NTF-001)', async ({ page }) => {
  note.read_at = null
  const reads = await mock(page)
  await page.goto('/')
  await page.getByRole('button', { name: 'EN' }).click()
  await page.getByRole('link', { name: '1 unread notification' }).click()
  await expect(page.getByText('Rice is at 20000 g, reorder point 30000')).toBeVisible()
  await page.getByRole('link', { name: 'Open' }).click()
  await expect.poll(() => reads.length).toBe(1)
})
