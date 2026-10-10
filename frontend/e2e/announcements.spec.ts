import { expect, type Route, test } from '@playwright/test'

test('a platform announcement shows until it is dismissed (FR-ADM-005)', async ({ page }) => {
  const posts: string[] = []
  let dismissed = false
  await page.route('**/api/v1/**', async (route: Route) => {
    const req = route.request()
    const path = new URL(req.url()).pathname
    if (req.method() === 'POST') {
      posts.push(path)
      dismissed = true
      return route.fulfill({ status: 204 })
    }
    const data: Record<string, unknown> = {
      '/api/v1/auth/session': {
        user: { id: 'u', email: 'a@x', name: 'Dewi', locale: 'en' },
        tenants: [{ id: 't', name: 'Dapur' }],
        active_tenant_id: 't',
        csrf_token: 'c',
        mfa_state: 'ok',
      },
      '/api/v1/me/capabilities': {
        tenant_id: 't',
        permissions: ['finance.report.view'],
        all_outlets: true,
        outlet_ids: [],
        modules: ['finance'],
        subscription: { state: 'active', days_left: null },
        nav: ['finance'],
        currency: 'IDR',
        language: 'id',
      },
      '/api/v1/outlets': [],
      '/api/v1/announcements': dismissed
        ? []
        : [
            {
              id: 'n1',
              level: 'warning',
              title: 'Maintenance tonight',
              body: 'The app is down 23:00-23:15 WIB.',
              ends_at: '2099-01-01T00:00:00Z',
            },
          ],
    }
    return path in data
      ? route.fulfill({ json: data[path] })
      : route.fulfill({ status: 404, json: { code: 'not_found' } })
  })
  await page.goto('/finance')
  await expect(page.getByRole('region', { name: 'Maintenance tonight' })).toBeVisible()
  await page.getByRole('button', { name: /Got it|Mengerti/ }).click()
  await expect(page.getByRole('region', { name: 'Maintenance tonight' })).toHaveCount(0)
  expect(posts).toEqual(['/api/v1/announcements/n1/dismiss'])
})
