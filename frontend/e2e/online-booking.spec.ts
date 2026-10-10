import { expect, type Page, test } from '@playwright/test'

const SLOTS = ['2030-01-02T10:00:00+07:00', '2030-01-02T10:30:00+07:00']

/** FR-TBL-010: the guest's public page; no session, the token is the only key. */
async function mock(page: Page, posts: unknown[], closed = false) {
  await page.route('**/api/v1/**', async (route) => {
    const req = route.request()
    const path = new URL(req.url()).pathname
    const json = (data: unknown, status = 200) => route.fulfill({ status, json: data })
    if (closed) return json({ code: 'booking_closed', message: 'closed' }, 404)
    if (path === '/api/v1/public/booking/tok-123456789012345678/slots') return json(SLOTS)
    if (path === '/api/v1/public/booking/tok-123456789012345678' && req.method() === 'POST') {
      posts.push({ body: req.postDataJSON(), key: req.headers()['idempotency-key'] })
      return json({ id: 'r1', starts_at: SLOTS[1], party_size: 2, status: 'pending' }, 201)
    }
    if (path === '/api/v1/public/booking/tok-123456789012345678') {
      return json({
        business: 'Dapur Sari',
        outlet: 'Kemang',
        timezone: 'Asia/Jakarta',
        max_party: 8,
        days_ahead: 30,
      })
    }
    return json({ code: 'unauthenticated', message: 'no' }, 401)
  })
}

test('a guest books a free time from the public link', async ({ page }) => {
  const posts: { body: Record<string, unknown>; key: string }[] = []
  await mock(page, posts)
  await page.goto('/book/tok-123456789012345678')
  await expect(page.getByRole('heading', { name: /Kemang/ })).toBeVisible()
  const book = page.getByRole('button', { name: /^(Book|Pesan)$/ })
  await expect(book).toBeDisabled()
  await page.getByRole('button', { name: /10[.:]30/ }).click()
  await page.getByLabel(/Your name|Nama Anda/).fill('Rina')
  await page.getByLabel(/Phone|Nomor HP/).fill('0813 1111 2222')
  await page.getByRole('checkbox').check()
  await book.click()
  await expect(page.getByRole('status')).toBeVisible()
  expect(posts).toHaveLength(1)
  expect(posts[0].body).toMatchObject({ name: 'Rina', starts_at: SLOTS[1], consent: true })
  expect(posts[0].key).toBeTruthy()
})

test('a switched-off link shows a closed page', async ({ page }) => {
  await mock(page, [], true)
  await page.goto('/book/tok-123456789012345678')
  await expect(page.getByRole('alert')).toBeVisible()
})
