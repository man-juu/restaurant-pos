import { expect, type Route, test } from '@playwright/test'

test('context help for the page and the changelog (FR-X-007)', async ({ page }) => {
  await page.route('**/api/v1/**', async (route: Route) => {
    const path = new URL(route.request().url()).pathname
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
      '/api/v1/announcements': [],
    }
    return path in data
      ? route.fulfill({ json: data[path] })
      : route.fulfill({ status: 404, json: { code: 'not_found' } })
  })
  await page.goto('/finance')
  await page.getByRole('button', { name: 'EN', exact: true }).click()
  await page.getByRole('button', { name: 'Help for this page' }).click()
  await expect(page.getByRole('dialog', { name: 'Money' })).toBeVisible()
  await expect(page.getByText(/prime cost \(food cost plus labour\)/)).toBeVisible()
  await page.getByRole('link', { name: /What's new/ }).click()
  await expect(page.getByRole('heading', { name: "What's new" })).toBeVisible()
  await expect(page.getByText('Notifications on your phone for the installed app')).toBeVisible()
})
