# Runbook: switch on free AI images (FR-CAT-013, ADR-022)

The feature is off until both values below are set. It is free only while the Cloudflare
account stays on the **Workers Free** plan: there, requests past the daily allowance fail with an
error instead of being billed. Never upgrade that account to a paid plan.

1. Create a free Cloudflare account (no credit card needed) or use the existing one.
2. Dashboard → My Profile → API Tokens → Create token → Custom token:
   permission **Account · Workers AI · Read** only, for that one account. Copy the token.
3. Copy the 32-character Account ID from the dashboard sidebar.
4. On the server, add to the environment file (never to Git):
   `AI_CF_ACCOUNT_ID=...` and `AI_CF_API_TOKEN=...`, then redeploy.
5. Check: the item screen shows "Create a photo with AI (free)" with "N images left today".

Limits (all in `backend/app/core/config.py`, change only with a reason):

| Setting | Default | Meaning |
| --- | --- | --- |
| `AI_DAILY_FREE_NEURONS` | 10000 | Cloudflare free allowance per UTC day |
| `AI_BUDGET_PERCENT` | 85 | stop here (buffer) |
| `AI_NEURONS_PER_IMAGE` | 60 | estimate for flux-1-schnell, 1024 px, 4 steps (~57.6) |
| `AI_TENANT_DAILY_IMAGES` | 10 | per business per day |

With the defaults: 8,500 / 60 = about 140 images a day for the whole platform.

If Cloudflare changes its free tier: set `AI_CF_API_TOKEN=` (empty) and redeploy; the feature
switches off at once. Before launch, re-check Cloudflare's statement that Workers AI does not
train on customer content.
