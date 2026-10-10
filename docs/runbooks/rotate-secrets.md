# Runbook: rotate secrets

Rotate at least yearly, immediately if a secret may have leaked or a person with access leaves.

| Secret | How | Downtime |
| --- | --- | --- |
| Database role passwords | `ALTER ROLE pos_app PASSWORD '...'` (as owner, via `docker compose exec db psql`), update the env file, `deploy.sh prod <current tag>` | Seconds |
| Deploy SSH key | New key pair; add the new public key to `deploy`'s `authorized_keys`; update `DEPLOY_SSH_KEY` in GitHub; remove the old key | None |
| Backup storage key | Create a new write-only key at the provider; update the env file; redeploy; delete the old key | None |
| Backup encryption key | New key pair on your computer; replace `backup-public-key.asc`; **keep the old private key** until all old backups have expired | None |
| `SECRET_ENCRYPTION_KEY` (2FA secrets) | Not rotatable yet without re-encrypting stored secrets; a re-encryption command will be added before the first rotation is needed. If it leaks: require every user to set up 2FA again | Planned |
| GitHub, Cloudflare, registrar, VPS accounts | Change password; keep 2FA on; review active sessions | None |

After any rotation, run the health check and sign in once.
