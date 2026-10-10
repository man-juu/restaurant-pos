import { expect, type Page, test } from '@playwright/test'

type Body = Record<string, unknown>

const outlets = [
  { id: 'shop', name: 'Shop', type: 'branch', timezone: 'Asia/Jakarta', is_active: true },
  {
    id: 'ck',
    name: 'Central kitchen',
    type: 'central_kitchen',
    timezone: 'Asia/Jakarta',
    is_active: true,
  },
]

const line = (status: string): Body => ({
  id: 'l1',
  item_id: 'i-beef',
  item_name: 'Beef',
  unit_code: 'g',
  requested_qty: '3000',
  approved_qty: '3000',
  shipped_qty: status === 'requested' ? null : '3000',
  received_qty: null,
  discrepancy_reason: null,
  value: 360000,
})

const transfer = (status: string): Body => ({
  id: 't1',
  number: 'TRF-2026-00001',
  from_outlet_id: 'ck',
  to_outlet_id: 'shop',
  status,
  needed_by: null,
  note: null,
  shipped_value: status === 'requested' ? 0 : 360000,
  adjustment_id: null,
  created_at: '2026-10-08T00:00:00Z',
  shipped_on: null,
  received_on: null,
  lines: [line(status)],
})

/** Fake transfers API: one shipped transfer waiting at the shop. */
async function mock(page: Page) {
  const sent: { path: string; body: Body }[] = []
  let current = transfer('shipped')
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
        permissions: ['transfers.transfer.view', 'transfers.transfer.receive', 'catalog.item.view'],
        all_outlets: true,
        outlet_ids: [],
        modules: ['inventory', 'transfers'],
        subscription: { state: 'active', days_left: null },
        nav: ['transfers'],
        currency: 'IDR',
        language: 'id',
      })
    if (path === '/api/v1/outlets') return json(outlets)
    if (path === '/api/v1/transfers') return json([current])
    if (req.method() === 'POST' && path === '/api/v1/transfers/t1/receive') {
      sent.push({ path, body: req.postDataJSON() as Body })
      current = { ...transfer('received'), adjustment_id: 'a1' }
      return json(current)
    }
    return json({}, 404)
  })
  return sent
}

test('shop receives a transfer with 200 g damaged (FR-TRF-003)', async ({ page }) => {
  const sent = await mock(page)
  await page.goto('/transfers')
  await page.getByRole('button', { name: 'EN' }).click()
  await expect(page.getByText('TRF-2026-00001 · Central kitchen → Shop')).toBeVisible()
  await expect(page.getByRole('link', { name: 'Delivery note (PDF)' })).toBeVisible()
  await page.getByLabel('Beef (g)').fill('2800')
  await page.getByLabel('Why less').selectOption('damaged')
  await page.getByRole('button', { name: 'Receive' }).click()
  await expect(page.getByText('Received', { exact: true })).toBeVisible()
  expect(sent[0].body.lines).toEqual([{ item_id: 'i-beef', qty: '2800', reason: 'damaged' }])
})
