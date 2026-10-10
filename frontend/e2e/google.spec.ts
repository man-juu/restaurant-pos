import { expect, type Route, test } from '@playwright/test'

test('login offers Sign in with Google when the server enables it (ADR 0.57)', async ({ page }) => {
  await page.route('**/api/v1/**', async (route: Route) => {
    const path = new URL(route.request().url()).pathname
    if (path === '/api/v1/auth/providers') return route.fulfill({ json: { google: true } })
    if (path === '/api/v1/auth/device') return route.fulfill({ status: 404, json: {} })
    return route.fulfill({ status: 401, json: { code: 'not_authenticated' } })
  })
  await page.goto('/login?google=no_account')
  await page.getByRole('button', { name: 'EN', exact: true }).click()
  const link = page.getByRole('link', { name: 'Sign in with Google' })
  await expect(link).toHaveAttribute('href', '/api/v1/auth/google/start')
  await expect(page.getByText('This Google account is not invited to any business.')).toBeVisible()
})
