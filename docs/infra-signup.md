# Infrastructure sign-up checklist

For slice 0.8. **Do not buy anything before then**: until deployment, everything runs locally and in CI for free. Prices and rules were found by web search on 2026-10-07 and are not confirmed; every line marked **(verify)** must be checked on the provider's own checkout page before paying. Constraint: no credit card, so every paid item must accept virtual account, e-wallet, QRIS or bank transfer.

## 1. What to buy, in order

| # | Item | Pick | Approx. cost | Pay with | Needed for |
| --- | --- | --- | --- | --- | --- |
| 1 | Domain | See section 2 | Rp15.000 to Rp200.000 per year | Registrar: VA, e-wallet, QRIS **(verify)** | Staging and production URLs, email |
| 2 | VPS | Biznet Gio NEO Lite MS 4.2 (2 cores, 4 GB, 60 GB) | ~Rp138.750 per month incl. tax | Prepaid balance **(verify top-up methods)** | Running the app |
| 3 | Backup storage | IDCloudHost Object Storage (S3-compatible) | ~Rp500 per GB per month; a few GB at launch | VA, retail outlets, QRIS | Off-site encrypted backups (Q-004) |
| 4 | Cloudflare | Free plan | Rp0 | none | DNS, TLS, DDoS protection, hiding the server IP |
| 5 | Transactional email | A free tier that needs no card **(verify)** | Rp0 | none | Invitations, password reset |
| 6 | Uptime and error tracking | Free tiers **(verify no card needed)** | Rp0 | none | Alerts |

Expected total: about **Rp140.000 to Rp150.000 per month**, plus the domain once a year. That's inside the Rp250.000 target.

**Why the backups go to a different provider from the VPS:** if the VPS account is lost, suspended or hacked, the backups must survive. IDCloudHost for storage and Biznet Gio for the VPS keeps them apart. Biznet Gio's own NEO Object Storage (~Rp1.000 per GB) is the fallback, but then a single account holds both the server and its backups.

## 2. Domain options (fewest documents first)

| Extension | Documents | Approx. price per year | Good for | Notes |
| --- | --- | --- | --- | --- |
| `.my.id` | None | Cheapest, ~Rp15.000 to Rp20.000 | Staging, testing | Reads as personal; fine for staging, weaker for a brand |
| `.biz.id` | None | Cheap | Production for a small business | Business-sounding, Indonesian |
| `.id` | Listed as none by some resellers, KTP by others **(verify with registrar)** | ~Rp200.000 to Rp300.000 **(verify)** | Production brand | Short and strong in Indonesia |
| `.com` | None (name, address, email only) | ~Rp137.000 promo, ~Rp201.000 renewal (Rumahweb) | Production brand, international | Easiest to buy; most recognisable |
| `.web.id` | KTP or passport | Cheap | | Only if you already have a KTP at hand |
| `.co.id` | KTP plus NIB, NPWP or company deed | Mid | | **Avoid for now**: needs a registered business |

**Recommendation:**
- **Production:** `.com`, or `.biz.id` if you want it cheaper and still business-like. Both need no ID documents.
- **Staging:** a subdomain of the production domain (`staging.yourname.com`) costs nothing extra. A separate `.my.id` is only worth buying if you want staging to be fully separate.
- Always check the **renewal** price, not just the first-year promo.
- Turn on registrar lock and two-factor login on the registrar account. Losing the domain means losing the app.

Buying `.com` through Cloudflare Registrar is at cost, but Cloudflare only takes cards or PayPal. So use an Indonesian registrar and point the nameservers to Cloudflare (free).

## 3. Sign-up steps

1. **Domain:** create a registrar account with two-factor login → buy → set the nameservers to the two Cloudflare gives you.
2. **Cloudflare:** free account with two-factor login → add the domain → SSL mode "Full (strict)" → turn on "Always Use HTTPS".
3. **VPS:** Biznet Gio account → top up the balance (check whether QRIS or transfer works for you) → create NEO Lite MS 4.2 with Ubuntu LTS in a Jakarta zone → add **your SSH public key** (no password login).
4. **Backup storage:** IDCloudHost account → create a private bucket → create an access key used only for backups. If the provider supports a write-only key, use one.
5. **Email, uptime, errors:** sign up for the free tiers. Record all accounts in a password manager, never in the repository.
6. **Send me nothing secret.** Give me the domain name and the server's public IP; secrets go straight into the server's protected environment file (slice 0.8 runbook).

## 4. Security that costs nothing (done in slice 0.8)

- Firewall: ports 80 and 443 only from Cloudflare IP ranges; SSH from your IPs only; root login and password login disabled.
- Automatic security updates; containers run as non-root; the database is never exposed to the internet.
- Encrypted nightly backups to a different provider, with a restore test every month.
- Two-factor login on every provider account (registrar, Cloudflare, VPS, storage, GitHub). Most real-world breaches of small projects start with an account login, not the server.
