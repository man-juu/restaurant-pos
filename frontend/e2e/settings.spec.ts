import { expect, type Page, test } from '@playwright/test'

const settings = {
  tax: {
    rules: [
      {
        id: 'pbjt',
        name: 'PBJT',
        rate_bp: 1000,
        applies_to_service_charge: true,
        price_includes_tax: false,
        order: 0,
        outlet_ids: null,
        active: true,
      },
    ],
  },
  service_charge: { enabled: false, rate_bp: 0, channels: [], before_tax: true },
  payment_methods: { methods: [{ code: 'cash', name: 'Tunai', kind: 'cash', active: true }] },
  numbering: { formats: { purchase_order: { prefix: 'PO', padding: 5, reset: 'yearly' } } },
  session: { idle_minutes: 60 },
}

async function mock(page: Page, permissions: string[]) {
  const saved: unknown[] = []
  await page.route('**/api/v1/**', async (route) => {
    const req = route.request()
    const path = new URL(req.url()).pathname
    const json = (body: unknown, status = 200) => route.fulfill({ status, json: body })
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
        permissions,
        all_outlets: true,
        outlet_ids: [],
        modules: [],
        subscription: { state: 'active', days_left: null },
        nav: [],
      })
    if (path === '/api/v1/settings') return json(settings)
    if (path === '/api/v1/settings/tax' && req.method() === 'PUT') {
      saved.push(req.postDataJSON())
      return json(req.postDataJSON())
    }
    if (path === '/api/v1/approval-rules' || path === '/api/v1/roles') return json([])
    return json({ code: 'not_found' }, 404)
  })
  return saved
}

test('owner edits a tax rate; invalid input cannot be saved', async ({ page }) => {
  const saved = await mock(page, ['tenant.settings.view', 'tenant.settings.configure'])
  await page.goto('/settings')
  await page.getByRole('button', { name: 'EN' }).click()
  const rate = page.getByLabel('Rate (%)')
  await rate.fill('12,5')
  await page.getByRole('button', { name: 'Save' }).click()
  await expect(page.getByRole('status').filter({ hasText: 'Saved' })).toBeVisible()
  expect(saved).toEqual([{ rules: [expect.objectContaining({ id: 'pbjt', rate_bp: 1250 })] }])
  await rate.fill('150')
  await expect(page.getByRole('button', { name: 'Save' })).toBeDisabled()
})

test('staff without configure permission see settings read-only', async ({ page }) => {
  await mock(page, ['tenant.settings.view'])
  await page.goto('/settings')
  await page.getByRole('button', { name: 'EN' }).click()
  await expect(page.getByText('Only owners and co-owners can change them.')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Save' })).toHaveCount(0)
  await expect(page.getByLabel('Rate (%)')).toBeDisabled()
})
