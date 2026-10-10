import { expect, type Page, test } from '@playwright/test'

const session = (mfa_state: string) => ({
  user: { id: 'u', email: 'owner@example.test', name: 'Rina', locale: 'id' },
  tenants: [
    { id: 't1', name: 'Dapur Sehat' },
    { id: 't2', name: 'Kopi Pagi' },
  ],
  active_tenant_id: mfa_state === 'ok' ? 't1' : null,
  csrf_token: 'csrf-token',
  mfa_state,
})

const capabilities = (nav: string[]) => ({
  tenant_id: 't1',
  permissions: ['tenant.outlet.view'],
  all_outlets: true,
  outlet_ids: [],
  modules: nav,
  subscription: { state: 'active', days_left: null },
  nav,
})

async function mockApi(page: Page, opts: { signedIn: boolean; nav?: string[] }) {
  let state = opts.signedIn ? 'ok' : 'none'
  await page.route('**/api/v1/**', async (route) => {
    const url = new URL(route.request().url())
    const json = (body: unknown, status = 200) => route.fulfill({ status, json: body })
    if (url.pathname === '/api/v1/auth/session') {
      return state === 'none' ? json({ code: 'not_authenticated' }, 401) : json(session(state))
    }
    if (url.pathname === '/api/v1/auth/login') {
      state = 'verify'
      return json(session('verify'))
    }
    if (url.pathname === '/api/v1/auth/mfa/verify') {
      expect(route.request().headers()['x-csrf-token']).toBe('csrf-token')
      state = 'ok'
      return json(session('ok'))
    }
    if (url.pathname === '/api/v1/me/capabilities') return json(capabilities(opts.nav ?? []))
    if (url.pathname === '/api/v1/outlets') return json([])
    return json({ code: 'not_found' }, 404)
  })
}

test('sign in with password and authenticator code', async ({ page }) => {
  await mockApi(page, { signedIn: false })
  await page.goto('/')
  await expect(page).toHaveURL(/\/login$/)
  await page.getByRole('button', { name: 'EN' }).click()
  await page.getByLabel('Email').fill('owner@example.test')
  await page.getByLabel('Password').fill('a long passphrase')
  await page.getByRole('button', { name: 'Continue' }).click()
  await page.getByLabel('Code').fill('123456')
  await page.getByRole('button', { name: 'Verify' }).click()
  await expect(page.getByRole('heading', { name: 'Welcome, Rina' })).toBeVisible()
})

test('language switch changes the UI and is remembered', async ({ page }) => {
  await mockApi(page, { signedIn: false })
  await page.goto('/login')
  await page.getByRole('button', { name: 'ID' }).click()
  await expect(page.getByRole('heading', { name: 'Masuk' })).toBeVisible()
  await page.getByRole('button', { name: 'EN' }).click()
  await expect(page.getByRole('heading', { name: 'Sign in' })).toBeVisible()
  await page.reload()
  await expect(page.getByRole('heading', { name: 'Sign in' })).toBeVisible()
  await expect(page.locator('html')).toHaveAttribute('lang', 'en')
})

test('navigation hides modules that are switched off', async ({ page }) => {
  await mockApi(page, { signedIn: true, nav: ['inventory'] })
  await page.goto('/')
  await page.getByRole('button', { name: 'EN' }).click()
  const nav = page.getByRole('navigation', { name: 'Main' }).filter({ visible: true })
  await expect(nav.getByRole('link', { name: 'Inventory' })).toBeVisible()
  await expect(nav.getByRole('link', { name: 'Purchasing' })).toHaveCount(0)
})

test('layout fits the screen without horizontal scrolling', async ({ page }) => {
  await mockApi(page, { signedIn: true, nav: ['inventory', 'purchasing'] })
  await page.goto('/')
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  )
  expect(overflow).toBeLessThanOrEqual(0)
})

test('appearance: light mode, accent swatch and background are applied and remembered', async ({
  page,
}) => {
  await mockApi(page, { signedIn: false })
  await page.goto('/login')
  await page.getByRole('button', { name: 'EN' }).click()
  await page.getByRole('button', { name: 'Appearance' }).click()
  await page.getByRole('button', { name: 'Light' }).click()
  await page.getByRole('button', { name: 'Lavender' }).click()
  await page.getByRole('button', { name: 'Dusk' }).click()
  await page.getByRole('button', { name: 'Done' }).click()
  const html = page.locator('html')
  await expect(html).toHaveAttribute('data-theme', 'light')
  await expect(html).toHaveAttribute('data-accent', 'lavender')
  await page.reload()
  await expect(html).toHaveAttribute('data-theme', 'light')
  const bg = await page.evaluate(() =>
    document.documentElement.style.getPropertyValue('--app-background'),
  )
  expect(bg).toContain('dusk.svg')
})
