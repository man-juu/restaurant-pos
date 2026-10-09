// Back-office load test (NFR-001, slice 1n). Run against a seeded API:
//   python -m tests.load.seed http://127.0.0.1:8000 > /tmp/load-seed.json
//   k6 run --no-usage-report -e SEED=/tmp/load-seed.json -e BASE=http://127.0.0.1:8000 tests/load/backoffice.js
// Reads and writes must meet p95 < 300 ms (NFR-001); reports are measured on their own.
import http from 'k6/http'
import { check, sleep } from 'k6'

const seed = JSON.parse(open(__ENV.SEED))
const BASE = __ENV.BASE || 'http://127.0.0.1:8000'

export const options = {
  scenarios: {
    staff: {
      executor: 'ramping-vus',
      stages: [
        { duration: '20s', target: Number(__ENV.VUS || 30) },
        { duration: __ENV.HOLD || '60s', target: Number(__ENV.VUS || 30) },
        { duration: '10s', target: 0 },
      ],
    },
  },
  thresholds: {
    'http_req_duration{kind:read}': ['p(95)<300'],
    'http_req_duration{kind:write}': ['p(95)<300'],
    // A daily sales entry posts and replaces a whole day for a channel (bulk document).
    'http_req_duration{kind:bulk}': ['p(95)<2000'],
    'http_req_duration{kind:report}': ['p(95)<2000'],
    http_req_failed: ['rate<0.01'],
  },
}

export function setup() {
  const res = http.post(`${BASE}/api/v1/auth/login`, JSON.stringify({ email: seed.email, password: seed.password }), {
    headers: { 'Content-Type': 'application/json' },
  })
  // The session cookie is Secure (__Host-); without TLS locally it is sent as a header.
  const cookie = res.headers['Set-Cookie'].split(';')[0]
  return { cookie, csrf: res.json('csrf_token') }
}

// Idempotency keys only need to be unique per request; no remote helper library needed.
const uuidv4 = () =>
  'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0
    return (c === 'x' ? r : (r & 0x3) | 0x8).toString(16)
  })

const day = (back) => new Date(Date.now() - back * 86400000).toISOString().slice(0, 10)

export default function (auth) {
  const headers = { Cookie: auth.cookie, 'X-CSRF-Token': auth.csrf, 'Content-Type': 'application/json' }
  const get = (path, kind) => http.get(`${BASE}${path}`, { headers, tags: { kind } })
  const r = Math.random()
  let res
  if (r < 0.25) res = get('/api/v1/me/capabilities', 'read')
  else if (r < 0.4) res = get('/api/v1/notifications/unread-count', 'read')
  else if (r < 0.55) res = get(`/api/v1/inventory/stock?outlet_id=${seed.outlet_id}`, 'read')
  else if (r < 0.7) res = get('/api/v1/catalog/items?limit=50', 'read')
  else if (r < 0.8) res = get(`/api/v1/sales/days/${seed.outlet_id}/${day(1)}`, 'read')
  else if (r < 0.88) {
    const ingredient = seed.ingredients[Math.floor(Math.random() * seed.ingredients.length)]
    const body = {
      outlet_id: seed.outlet_id,
      business_date: day(0),
      reason_code: 'spoilage',
      lines: [{ item_id: ingredient, qty: '1', unit_id: seed.gram }],
    }
    res = http.post(`${BASE}/api/v1/inventory/waste`, JSON.stringify(body), {
      headers: { ...headers, 'Idempotency-Key': uuidv4() },
      tags: { kind: 'write' },
    })
  } else if (r < 0.92) {
    const lines = seed.menu.slice(0, 5).map((m) => ({ item_id: m, qty: String(1 + Math.floor(Math.random() * 9)) }))
    const body = { outlet_id: seed.outlet_id, business_date: day(Math.ceil(Math.random() * 30)), channel_id: seed.channel_id, lines }
    res = http.post(`${BASE}/api/v1/sales/days/entries`, JSON.stringify(body), {
      headers: { ...headers, 'Idempotency-Key': uuidv4() },
      tags: { kind: 'bulk' },
    })
  } else res = get(`/api/v1/sales/reports/summary?from=${day(30)}&to=${day(0)}&grain=day`, 'report')
  check(res, { ok: (x) => x.status < 400 })
  // THINK=1 adds 1 to 3 s between actions, like a person; THINK=0 is a stress test.
  if (__ENV.THINK !== '0') sleep(1 + Math.random() * 2)
}
