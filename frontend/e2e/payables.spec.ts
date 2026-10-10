import { expect, test } from '@playwright/test'

type Body = Record<string, unknown>

const bill = {
  id: 'b1',
  number: 'BILL-2026-00001',
  vendor_id: 'v1',
  vendor_invoice_no: 'INV-77',
  outlet_id: 'o1',
  po_id: 'po1',
  bill_date: '2026-03-05',
  due_date: '2026-03-05',
  total: 1575000,
  paid: 0,
  credited: 0,
  balance: 1575000,
  status: 'open',
  match_status: 'mismatch',
  match_notes: [
    {
      item_id: 'i-rice',
      issue: 'price_over_po',
      billed_qty: '25000',
      received_qty: '25000',
      billed_unit_price: '15',
      po_unit_price: '14',
    },
  ],
  receipt_ids: ['r1'],
  note: null,
  lines: [],
  payments: [],
}

test('accountant sees a flagged bill and records a payment (FR-PUR-009)', async ({ page }) => {
  const posted: Body[] = []
  const routes: Record<string, (body: Body) => unknown> = {
    'GET /api/v1/outlets': () => [
      { id: 'o1', name: 'Toko', type: 'outlet', timezone: 'Asia/Jakarta', is_active: true },
    ],
    'GET /api/v1/purchasing/vendors': () => [{ id: 'v1', name: 'CV Segar', is_active: true }],
    'GET /api/v1/purchasing/bills': () => [bill],
    'GET /api/v1/purchasing/payables': () => [
      {
        bill_id: 'b1',
        number: bill.number,
        vendor_id: 'v1',
        vendor_invoice_no: 'INV-77',
        due_date: '2026-03-05',
        balance: 1575000,
        days_overdue: 3,
      },
    ],
    'GET /api/v1/purchasing/returns': () => [],
    'GET /api/v1/purchasing/receipts': () => [],
    'GET /api/v1/settings': () => ({
      payment_methods: {
        methods: [{ code: 'transfer', name: 'Transfer', kind: 'bank_transfer', active: true }],
      },
    }),
    'POST /api/v1/purchasing/bills/b1/payments': (body) => {
      posted.push(body)
      return {
        ...bill,
        paid: body.amount,
        balance: 1575000 - Number(body.amount),
        status: 'partially_paid',
      }
    },
  }
  await page.route('**/api/v1/**', async (route) => {
    const req = route.request()
    const path = new URL(req.url()).pathname
    const json = (data: unknown, status = 200) => route.fulfill({ status, json: data })
    if (path === '/api/v1/auth/session')
      return json({
        user: { id: 'u', email: 'a@x', name: 'Ani', locale: 'en' },
        tenants: [{ id: 't', name: 'Dapur' }],
        active_tenant_id: 't',
        csrf_token: 'c',
        mfa_state: 'ok',
      })
    if (path === '/api/v1/me/capabilities')
      return json({
        tenant_id: 't',
        permissions: ['purchasing.vendor.view', 'purchasing.bill.view', 'purchasing.bill.pay'],
        all_outlets: true,
        outlet_ids: [],
        modules: ['purchasing'],
        subscription: { state: 'active', days_left: null },
        nav: ['purchasing'],
        currency: 'IDR',
        language: 'id',
      })
    const handler = routes[`${req.method()} ${path}`]
    return handler
      ? json(handler((req.postDataJSON() ?? {}) as Body))
      : json({ code: 'not_found' }, 404)
  })
  await page.goto('/purchasing')
  await page.getByRole('button', { name: 'EN', exact: true }).click()
  await page.getByRole('tab', { name: 'Bills' }).click()
  await expect(page.getByText('1 bill overdue', { exact: false })).toBeVisible()
  await expect(page.getByText('Billed price 15 is above the order price 14.')).toBeVisible()
  await page.getByLabel('Amount').fill('500000')
  await page.getByRole('button', { name: 'Record payment' }).click()
  await expect.poll(() => posted[0]).toMatchObject({ amount: 500000, method: 'transfer' })
})
