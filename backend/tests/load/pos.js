// Cashier load test (slice 2l, NFR-001 and NFR-002). Run against a seeded API:
//   python -m tests.load.seed_pos http://127.0.0.1:8000 > /tmp/pos-seed.json
//   k6 run --no-usage-report -e SEED=/tmp/pos-seed.json -e BASE=http://127.0.0.1:8000 tests/load/pos.js
// Each virtual user is a till at one of the outlets: open an order, ring up 1 to 4 items,
// take cash. "order_end_to_end" sums the server time of those calls (NFR-002: under 1 s).
import http from "k6/http";
import { check, sleep } from "k6";
import { Trend } from "k6/metrics";

const seed = JSON.parse(open(__ENV.SEED));
const BASE = __ENV.BASE || "http://127.0.0.1:8000";
const THINK = Number(__ENV.THINK ?? 1);
const endToEnd = new Trend("order_end_to_end", true);

export const options = {
  scenarios: {
    tills: {
      executor: "ramping-vus",
      stages: [
        { duration: "20s", target: Number(__ENV.VUS || 16) },
        { duration: __ENV.HOLD || "60s", target: Number(__ENV.VUS || 16) },
        { duration: "10s", target: 0 },
      ],
    },
  },
  thresholds: {
    "http_req_duration{kind:create}": ["p(95)<300"],
    "http_req_duration{kind:line}": ["p(95)<300"],
    "http_req_duration{kind:pay}": ["p(95)<300"],
    order_end_to_end: ["p(95)<1000"],
    http_req_failed: ["rate<0.01"],
  },
};

export function setup() {
  const res = http.post(
    `${BASE}/api/v1/auth/login`,
    JSON.stringify({ email: seed.email, password: seed.password }),
    { headers: { "Content-Type": "application/json" } },
  );
  // The session cookie is Secure (__Host-); without TLS locally it is sent as a header.
  return { cookie: res.headers["Set-Cookie"].split(";")[0], csrf: res.json("csrf_token") };
}

const uuidv4 = () =>
  "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    return (c === "x" ? r : (r & 0x3) | 0x8).toString(16);
  });

export default function (auth) {
  const outlet = seed.outlets[(__VU - 1) % seed.outlets.length];
  const post = (path, body, kind) =>
    http.post(`${BASE}${path}`, JSON.stringify(body), {
      headers: {
        Cookie: auth.cookie,
        "X-CSRF-Token": auth.csrf,
        "Content-Type": "application/json",
        "Idempotency-Key": uuidv4(),
      },
      tags: { kind },
    });
  let spent = 0;
  const made = post("/api/v1/pos/orders", { outlet_id: outlet, channel_id: seed.channel_id }, "create");
  spent += made.timings.duration;
  if (!check(made, { "order created": (r) => r.status === 201 })) return;
  const order = made.json("id");
  let last = made;
  const items = 1 + Math.floor(Math.random() * 4);
  for (let i = 0; i < items; i++) {
    sleep(THINK * (0.5 + Math.random()));
    const dish = seed.menu[Math.floor(Math.random() * seed.menu.length)];
    last = post(`/api/v1/pos/orders/${order}/lines`, { item_id: dish, qty: "1" }, "line");
    spent += last.timings.duration;
    check(last, { "line added": (r) => r.status === 200 });
  }
  sleep(THINK * (1 + Math.random()));
  const total = last.json("totals.total") ?? last.json("total");
  const paid = post(
    `/api/v1/pos/orders/${order}/pay`,
    { payments: [{ method: "cash", amount: total, tendered: total }] },
    "pay",
  );
  spent += paid.timings.duration;
  if (check(paid, { paid: (r) => r.status === 200 })) endToEnd.add(spent);
  sleep(THINK * 2);
}
