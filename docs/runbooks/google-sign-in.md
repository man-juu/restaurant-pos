# Sign in with Google (ADR 0.57)

Free. No credit card or billing account. Takes about 10 minutes, once.

## Set up

1. Go to https://console.cloud.google.com and sign in with the business Google account.
2. Create a project, for example "Restaurant POS".
3. **APIs & Services → OAuth consent screen**: user type **External**, app name, support email.
   Scopes: only `openid`, `email`, `profile` (these need no Google review). Publish the app
   ("In production"), otherwise only test users can sign in.
4. **APIs & Services → Credentials → Create credentials → OAuth client ID**:
   - Application type: **Web application**.
   - Authorised redirect URI: `https://<your domain>/api/v1/auth/google/callback`
     (local: `http://localhost:5173/api/v1/auth/google/callback`).
5. Copy the client ID and secret into the server's `.env` as `GOOGLE_CLIENT_ID` and
   `GOOGLE_CLIENT_SECRET`, then redeploy. Never commit them.

The login page shows "Sign in with Google" once both are set.

## How it behaves

- Only people the owner invited can sign in, matched by their verified Google email.
  Google never creates an account.
- Owners and co-owners still enter their 2FA code after Google.
- Password and PIN sign-in keep working. If Google is down or the client is disabled, only the
  Google button stops working.
- Google receives no business data: only that this person signed in to this app.

## Turning it off or rotating the secret

Clear the two values (off), or create a new secret in the console, update `.env`, redeploy and
delete the old secret (see `rotate-secrets.md`).
