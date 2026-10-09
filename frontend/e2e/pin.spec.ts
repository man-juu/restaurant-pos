import { expect, type Route, test } from '@playwright/test'

test('on a registered till, staff sign in with their PIN (FR-IDN-004)', async ({ page }) => {
  let signedIn = false
  const posts: { path: string; body: unknown }[] = []
  const session = {
    user: { id: 'u2', email: 'c@x', name: 'Sari', locale: 'en' },
    tenants: [{ id: 't', name: 'Dapur' }],
    active_tenant_id: 't',
    csrf_token: 'c',
    mfa_state: 'ok',
  }
  await page.route('**/api/v1/**', async (route: Route) => {
    const req = route.request()
    const path = new URL(req.url()).pathname
    if (req.method() !== 'GET') posts.push({ path, body: req.postDataJSON() })
    if (path === '/api/v1/auth/session')
      return signedIn
        ? route.fulfill({ json: session })
        : route.fulfill({ status: 401, json: { code: 'not_authenticated' } })
    if (path === '/api/v1/auth/device')
      return route.fulfill({
        json: { name: 'Front till', outlet_id: null, staff: [{ user_id: 'u2', name: 'Sari' }] },
      })
    if (path === '/api/v1/auth/pin-login') {
      signedIn = true
      return route.fulfill({ json: session })
    }
    if (path === '/api/v1/me/capabilities')
      return route.fulfill({
        json: {
          tenant_id: 't',
          permissions: [],
          all_outlets: false,
          outlet_ids: [],
          modules: [],
          subscription: { state: 'active', days_left: null },
          nav: [],
          currency: 'IDR',
          language: 'id',
        },
      })
    return route.fulfill({ status: 404, json: { code: 'not_found' } })
  })
  await page.goto('/login')
  await page.getByRole('button', { name: 'EN' }).click()
  await expect(page.getByText('This till: Front till. Tap your name.')).toBeVisible()
  await page.getByRole('button', { name: 'Sari' }).click()
  for (const digit of ['1', '2', '3', '4'])
    await page.getByRole('button', { name: digit, exact: true }).click()
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
  await expect(page).toHaveURL(/\/$/)
  expect(posts.at(-1)).toEqual({
    path: '/api/v1/auth/pin-login',
    body: { user_id: 'u2', pin: '1234' },
  })
})
