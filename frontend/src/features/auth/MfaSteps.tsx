import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Alert, Button, Card, Field } from '../../components/ui'
import { errorMessage } from '../../lib/errors'
import {
  useLogout,
  useMfaConfirm,
  useMfaSetup,
  useReloadSession,
  useVerifyMfa,
} from '../../lib/session'

function CodeForm({
  title,
  help,
  pending,
  error,
  onSubmit,
}: {
  title: string
  help: string
  pending: boolean
  error: unknown
  onSubmit: (code: string) => void
}) {
  const { t } = useTranslation()
  const [recovery, setRecovery] = useState(false)
  const [code, setCode] = useState('')
  const logout = useLogout()
  return (
    <Card className="flex flex-col gap-4">
      <div>
        <h3 className="font-bold">{title}</h3>
        <p className="text-sm text-muted">{help}</p>
      </div>
      {error ? <Alert>{errorMessage(error, t)}</Alert> : null}
      <form
        className="flex flex-col gap-3"
        onSubmit={(e) => {
          e.preventDefault()
          onSubmit(code)
        }}
      >
        <Field
          label={recovery ? t('auth.recoveryCode') : t('auth.code')}
          inputMode={recovery ? 'text' : 'numeric'}
          autoComplete="one-time-code"
          value={code}
          onChange={(e) => setCode(e.target.value)}
        />
        <Button type="submit" disabled={pending} aria-busy={pending}>
          {pending ? t('auth.working') : t('auth.verify')}
        </Button>
      </form>
      {!recovery && (
        <button
          type="button"
          className="min-h-11 text-left text-sm text-accent"
          onClick={() => setRecovery(true)}
        >
          {t('auth.useRecovery')}
        </button>
      )}
      {/* User control and freedom: a way back out of the 2FA step. */}
      <button
        type="button"
        className="min-h-11 text-left text-sm text-ink-soft underline"
        onClick={() => logout.mutate()}
      >
        {t('auth.otherAccount')}
      </button>
    </Card>
  )
}

export function VerifyStep() {
  const { t } = useTranslation()
  const verify = useVerifyMfa()
  return (
    <CodeForm
      title={t('auth.codeTitle')}
      help={t('auth.codeHelp')}
      pending={verify.isPending}
      error={verify.error}
      onSubmit={(code) => verify.mutate({ code })}
    />
  )
}

export function EnrollStep({ onCodes }: { onCodes: (codes: string[]) => void }) {
  const { t } = useTranslation()
  const setup = useMfaSetup()
  const confirm = useMfaConfirm()
  if (!setup.data) {
    return (
      <Card className="flex flex-col gap-4">
        <h3 className="font-bold">{t('auth.enrollTitle')}</h3>
        <p className="text-sm text-ink-soft">{t('auth.enrollHelp')}</p>
        {setup.error ? <Alert>{errorMessage(setup.error, t)}</Alert> : null}
        <Button onClick={() => setup.mutate()} disabled={setup.isPending}>
          {t('auth.startEnroll')}
        </Button>
      </Card>
    )
  }
  return (
    <div className="flex flex-col gap-4">
      <Card className="flex flex-col gap-2">
        <p className="text-sm font-semibold text-ink-soft">{t('auth.secretLabel')}</p>
        <code className="rounded-lg bg-ground p-3 font-mono text-base tracking-widest break-all">
          {setup.data.secret}
        </code>
        <a className="text-sm text-accent" href={setup.data.otpauth_uri}>
          {t('auth.openApp')}
        </a>
      </Card>
      <CodeForm
        title={t('auth.codeTitle')}
        help={t('auth.codeHelp')}
        pending={confirm.isPending}
        error={confirm.error}
        onSubmit={(code) =>
          confirm.mutate({ code }, { onSuccess: (data) => onCodes(data.recovery_codes) })
        }
      />
    </div>
  )
}

export function RecoveryCodes({ codes, onDone }: { codes: string[]; onDone: () => void }) {
  const { t } = useTranslation()
  const reload = useReloadSession()
  return (
    <Card className="flex flex-col gap-4">
      <h3 className="font-bold">{t('auth.recoveryTitle')}</h3>
      <p className="text-sm text-ink-soft">{t('auth.recoveryHelp')}</p>
      <ul className="grid grid-cols-2 gap-2 font-mono text-sm">
        {codes.map((code) => (
          <li key={code} className="rounded-lg bg-ground px-3 py-2 text-center">
            {code}
          </li>
        ))}
      </ul>
      <Button
        onClick={() => {
          void reload()
          onDone()
        }}
      >
        {t('auth.recoverySaved')}
      </Button>
    </Card>
  )
}
