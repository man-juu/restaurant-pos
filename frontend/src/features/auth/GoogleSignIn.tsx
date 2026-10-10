import { useTranslation } from 'react-i18next'
import { useSearchParams } from 'react-router'

import { Alert } from '../../components/ui'
import { useProviders } from '../../lib/session'

const MESSAGES: Record<string, string> = {
  no_account: 'auth.google.noAccount',
  locked: 'auth.google.locked',
}

/** ADR 0.57: a full-page link, not a fetch: Google's page must open in this tab. */
export function GoogleSignIn() {
  const { t } = useTranslation()
  const providers = useProviders()
  const [params] = useSearchParams()
  const problem = params.get('google')
  if (!providers.data?.google) return null
  return (
    <div className="flex flex-col gap-3">
      {problem && <Alert>{t(MESSAGES[problem] ?? 'auth.google.failed')}</Alert>}
      <a
        href="/api/v1/auth/google/start"
        className="inline-flex min-h-13 items-center justify-center gap-2 rounded-xl border border-line-strong bg-card px-4 font-display text-base font-extrabold text-ink hover:bg-raised"
      >
        {t('auth.google.button')}
      </a>
      <p className="text-center text-sm text-ink-soft">{t('auth.google.or')}</p>
    </div>
  )
}
