import { zodResolver } from '@hookform/resolvers/zod'
import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import { Navigate } from 'react-router'
import { z } from 'zod'

import { AppearanceMenu } from '../../components/AppearanceMenu'
import { LanguageSwitch } from '../../components/LanguageSwitch'
import { Alert, Button, Card, Field, Logo } from '../../components/ui'
import { errorMessage } from '../../lib/errors'
import { useAppearance } from '../../lib/theme'
import {
  useLogin,
  useLogout,
  useMfaConfirm,
  useMfaSetup,
  useReloadSession,
  useSession,
  useVerifyMfa,
} from '../../lib/session'

const credentials = z.object({ email: z.string().email(), password: z.string().min(1) })
type Credentials = z.infer<typeof credentials>

export function LoginPage() {
  const { t } = useTranslation()
  const session = useSession()
  const [codes, setCodes] = useState<string[] | null>(null)
  const appearance = useAppearance()

  if (session.data?.mfa_state === 'ok' && !codes) return <Navigate to="/" replace />
  const state = session.data?.mfa_state

  return (
    <div className="flex min-h-screen flex-wrap bg-ground">
      <section
        data-theme="dark"
        data-accent={appearance.accent}
        className="relative flex min-w-0 flex-[1_1_560px] flex-col justify-between gap-10 overflow-hidden bg-[#0f151c] bg-cover bg-center px-6 py-10 text-[#e6edf3] [background-image:var(--app-background)] sm:px-16 sm:py-14"
      >
        {/* The hero sits on the chosen background image with a dark scrim, so its text stays
            readable in light and dark mode alike. */}
        <div
          aria-hidden="true"
          className="absolute inset-0 bg-gradient-to-r from-[#0f151c]/85 to-[#0f151c]/35"
        />
        <div className="relative flex items-center gap-3">
          <Logo />
          <span className="font-display text-xl font-bold">{t('app.title')}</span>
        </div>
        <div className="relative max-w-xl">
          <span className="inline-flex items-center gap-2 rounded-full border border-white/20 px-3 py-1.5 text-sm text-[#c9d4de]">
            <span className="h-2 w-2 rounded-full bg-accent" />
            {t('app.badge')}
          </span>
          <h1 className="mt-5 font-display text-4xl leading-none font-extrabold tracking-tight sm:text-6xl">
            {t('app.tagline')} <span className="text-accent">{t('app.taglineAccent')}</span>
          </h1>
          <p className="mt-4 text-lg leading-relaxed text-[#c9d4de]">{t('app.pitch')}</p>
        </div>
        <span />
      </section>
      <section className="flex min-w-0 flex-[1_1_420px] items-center justify-center border-l border-line bg-panel px-6 py-12">
        <div className="flex w-full max-w-sm flex-col gap-7">
          <div className="flex items-center justify-between">
            <h2 className="font-display text-3xl font-bold">{t('auth.signIn')}</h2>
            <div className="flex items-center gap-2">
              <LanguageSwitch />
              <AppearanceMenu />
            </div>
          </div>
          {codes ? (
            <RecoveryCodes codes={codes} onDone={() => setCodes(null)} />
          ) : state === 'verify' ? (
            <VerifyStep />
          ) : state === 'enroll' ? (
            <EnrollStep onCodes={setCodes} />
          ) : (
            <PasswordStep />
          )}
        </div>
      </section>
    </div>
  )
}

function PasswordStep() {
  const { t } = useTranslation()
  const login = useLogin()
  const [showPassword, setShowPassword] = useState(false)
  const form = useForm<Credentials>({ resolver: zodResolver(credentials) })
  return (
    <form
      className="flex flex-col gap-4"
      onSubmit={form.handleSubmit((values) => login.mutate(values))}
      noValidate
    >
      {login.error && <Alert>{errorMessage(login.error, t)}</Alert>}
      <Field
        label={t('auth.email')}
        type="email"
        autoComplete="username"
        {...form.register('email')}
      />
      <Field
        label={t('auth.password')}
        type={showPassword ? 'text' : 'password'}
        autoComplete="current-password"
        {...form.register('password')}
        trailing={
          <button
            type="button"
            onClick={() => setShowPassword((v) => !v)}
            aria-pressed={showPassword}
            className="min-h-10 rounded-lg px-3 text-sm font-bold text-accent"
          >
            {showPassword ? t('auth.hidePassword') : t('auth.showPassword')}
          </button>
        }
      />
      <Button
        type="submit"
        disabled={login.isPending}
        aria-busy={login.isPending}
        className="min-h-13 text-base"
      >
        {login.isPending ? t('auth.working') : t('auth.continue')}
      </Button>
    </form>
  )
}

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

function VerifyStep() {
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

function EnrollStep({ onCodes }: { onCodes: (codes: string[]) => void }) {
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

function RecoveryCodes({ codes, onDone }: { codes: string[]; onDone: () => void }) {
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
