# Runbook: set up a new server (once per server)

For the 4 GB VPS chosen in `docs/infra-signup.md`. Allow about 1 hour. Steps marked 👤 need your accounts.

## 1. Server basics (Ubuntu LTS)

1. 👤 Create the VPS with **your SSH public key** (no password login). Note its public IP.
2. Log in: `ssh root@<ip>`, then:
   ```sh
   apt update && apt -y full-upgrade
   apt -y install unattended-upgrades ufw fail2ban curl ca-certificates
   dpkg-reconfigure -plow unattended-upgrades          # automatic security updates
   timedatectl set-ntp true                            # correct time matters for 2FA codes
   # One account and one key per environment, so the staging key can never deploy production.
   for env in staging prod; do
     adduser --disabled-password --gecos "" deploy-$env
     install -d -m 700 -o deploy-$env -g deploy-$env /home/deploy-$env/.ssh
   done
   ```
   In `/home/deploy-<env>/.ssh/authorized_keys` (mode 600, owned by that user) put the PUBLIC half of that environment's key, prefixed with a forced command, so the key can do nothing except deploy a tag to its own environment:
   ```
   restrict,command="sudo /opt/restaurant-pos/deploy.sh staging \"$SSH_ORIGINAL_COMMAND\"" ssh-ed25519 AAAA... staging-deploy
   ```
   (and `... deploy.sh prod ...` with the production key for `deploy-prod`).
3. SSH hardening in `/etc/ssh/sshd_config`: `PermitRootLogin no`, `PasswordAuthentication no`, then `systemctl restart ssh`. Keep your current session open and test a new login before closing it.
4. Firewall: SSH from your IPs, web only from Cloudflare (so nobody can bypass Cloudflare):
   ```sh
   ufw default deny incoming && ufw default allow outgoing
   ufw allow from <your-home-ip> to any port 22 proto tcp
   for ip in $(curl -s https://www.cloudflare.com/ips-v4) $(curl -s https://www.cloudflare.com/ips-v6); do
     ufw allow from "$ip" to any port 80,443 proto tcp
   done
   ufw enable
   ```
   Then check from another network that the origin is closed: `curl -m 5 https://<server-ip>` must time out.
   **Important:** ports published by Docker (80 and 443 of the web container) bypass ufw. So also set the same rules in the **VPS provider's cloud firewall** (IDCloudHost, Biznet Gio and Hostinger all offer one): 22 from your IP, 80/443 from Cloudflare ranges only, everything else closed. The provider firewall is the one that really protects the published ports.

## 2. Docker and the app folder

```sh
curl -fsSL https://get.docker.com | sh                 # official Docker install script
install -d -m 755 /opt/restaurant-pos /etc/restaurant-pos
# copy from the repository: infra/compose.prod.yaml, infra/db/init/, infra/scripts/deploy.sh
chmod 700 /opt/restaurant-pos/deploy.sh
cat > /etc/sudoers.d/restaurant-pos <<'SUDO'
deploy-staging ALL=(root) NOPASSWD: /opt/restaurant-pos/deploy.sh staging *
deploy-prod    ALL=(root) NOPASSWD: /opt/restaurant-pos/deploy.sh prod *
SUDO
chmod 440 /etc/sudoers.d/restaurant-pos                # each user may run ONLY its own deploy
```

Log in to the registry once (a GitHub token with `read:packages` only): `docker login ghcr.io`.

## 3. Secrets (never in Git)

Create `/etc/restaurant-pos/prod.env` (and `staging.env` with different values), `chmod 600`, owned by root:

```sh
APP_DOMAIN=app.<your-domain>
ADMIN_DOMAIN=admin.<your-domain>
ADMIN_ALLOWED_IPS=<your-home-ip>/32
ACME_EMAIL=<your-email>
POSTGRES_PASSWORD=<openssl rand -hex 24>
APP_DB_PASSWORD=<openssl rand -hex 24>
READONLY_DB_PASSWORD=<openssl rand -hex 24>
ADMIN_DB_PASSWORD=<openssl rand -hex 24>
SECRET_ENCRYPTION_KEY=<openssl rand -base64 32>      # losing it disables everyone's 2FA
BACKUP_S3_ENDPOINT=https://<object-storage-endpoint>
BACKUP_S3_BUCKET=<bucket>
BACKUP_S3_REGION=<region>
BACKUP_S3_ACCESS_KEY=<write-only key>
BACKUP_S3_SECRET_KEY=<secret>
BACKUP_PREFIX=prod
```

Staging: before launch, run the **staging** stack on this VPS to rehearse. Once production is live, staging needs its own small VPS (two stacks cannot both own ports 80/443), or staging is skipped and releases go straight to production after CI and a local `docker compose` run.

Copy `SECRET_ENCRYPTION_KEY` and all passwords into your password manager.

## 4. Cloudflare

1. 👤 DNS: `A app` and `A admin` to the server IP, **proxied** (orange cloud).
2. SSL/TLS mode **Full (strict)**; Caddy gets real certificates automatically.
3. Add one free **rate limiting rule** for `/api/v1/auth/*` (for example 20 requests per minute per IP); the app also locks accounts and IPs itself.

## 5. Backups key (on YOUR computer, not the server)

```sh
gpg --quick-gen-key "Restaurant POS backups" default default never
gpg --armor --export "Restaurant POS backups" > backup-public-key.asc
```
Copy only `backup-public-key.asc` to `/etc/restaurant-pos/backup-public-key.asc` on the server. Keep the private key in your password manager and an offline copy: without it, backups cannot be restored.

## 6. GitHub settings

1. Settings → Environments: create `staging` and `production`. Put the secrets in **each environment** (not repository-wide), so only that environment's job can read its key:
   `DEPLOY_SSH_KEY` (private half of that environment's key), `DEPLOY_HOST` (server IP), `DEPLOY_KNOWN_HOSTS` (`ssh-keyscan -t ed25519 <ip>`, compared with the fingerprint shown on the server's console). On `production` also set **Deployment branches and tags: tags `v*` only**, and required reviewers if your plan offers them.
2. Settings → Rules → Rulesets: protect tags `v*` so only you can create them, and protect `main` (pull request + green CI).
3. Variable `STAGING_URL`.

## 7. First deployment

Push a tag (`git tag v0.1.0 && git push origin v0.1.0`), watch **Release**, then create the first admin:
`docker compose -p pos-prod --env-file /etc/restaurant-pos/prod.env -f /opt/restaurant-pos/compose.prod.yaml exec api python -m app.admin.cli create-admin you@example.com "Your Name" super_admin`.
