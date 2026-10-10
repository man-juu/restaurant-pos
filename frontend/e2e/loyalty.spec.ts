import { expect, type Page, test } from '@playwright/test'

const GUEST = { id: 'g1', name: 'Sari', phone: '62812111222', note: null, consent_at: '2026-10-01' }

async function mock(page: Page, posts: unknown[]) {
  await page.route('**/api/v1/**', async (route) => {
    const req = route.request()
    const path = new URL(req.url()).pathname
    const json = (data: unknown, status = 200) => route.fulfill({ status, json: data })
    if (req.method() === 'POST' && path === '/api/v1/loyalty/redeem') {
      posts.push(req.postDataJSON())
      return json(
        {
          id: 'v1',
          code: 'ABCD-EFGH',
          amount: 10000,
          customer_id: 'g1',
          points: 100,
          note: null,
          expires_on: null,
          status: 'active',
          used_document_id: null,
          created_at: '2026-10-10T10:00:00Z',
        },
        201,
      )
    }
    const data: Record<string, unknown> = {
      '/api/v1/auth/session': {
        user: { id: 'u', email: 'c@x', name: 'Rina', locale: 'en' },
        tenants: [{ id: 't', name: 'Dapur' }],
        active_tenant_id: 't',
        csrf_token: 'c',
        mfa_state: 'ok',
      },
      '/api/v1/me/capabilities': {
        tenant_id: 't',
        permissions: ['loyalty.points.view', 'loyalty.points.redeem'],
        all_outlets: true,
        outlet_ids: [],
        modules: ['sales', 'loyalty'],
        subscription: { state: 'active', days_left: null },
        nav: ['loyalty'],
        currency: 'IDR',
        language: 'id',
      },
      '/api/v1/customers': [GUEST],
      '/api/v1/loyalty/customers/g1': {
        customer_id: 'g1',
        balance: 150,
        point_value: 100,
        min_redeem_points: 100,
        entries: [
          {
            id: 'e1',
            kind: 'earn',
            points: 150,
            document_id: 'd1',
            voucher_id: null,
            created_at: '2026-10-09T10:00:00Z',
          },
        ],
        vouchers: [],
      },
    }
    return path in data ? json(data[path]) : json({ code: 'not_found' }, 404)
  })
}

test('cashier turns a guest’s points into a voucher (FR-SAL-016)', async ({ page }) => {
  const posts: unknown[] = []
  await mock(page, posts)
  await page.goto('/loyalty')
  await page.getByRole('button', { name: 'EN', exact: true }).click()
  await page.getByLabel('Guest phone or name').fill('0812')
  await page.getByRole('button', { name: /Sari/ }).click()
  await expect(page.getByText(/150 points/)).toBeVisible()
  await page.getByLabel(/Points to use/).fill('100')
  await page.getByRole('button', { name: 'Make voucher' }).click()
  await expect(page.getByText('Voucher code: ABCD-EFGH')).toBeVisible()
  expect(posts.at(-1)).toEqual({ customer_id: 'g1', points: 100 })
})
