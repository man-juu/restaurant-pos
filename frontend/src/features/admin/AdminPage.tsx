import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { AppearanceMenu } from '../../components/AppearanceMenu'
import { LanguageSwitch } from '../../components/LanguageSwitch'
import { Alert, Button, Card, Field, Logo, StateBadge } from '../../components/ui'
import { ApiError, request, setCsrfToken } from '../../lib/api/client'
import type { AdminSessionOut, TenantOut } from '../../lib/api/types'
import { errorMessage } from '../../lib/errors'
import { TenantOps } from './TenantOps'
import { TenantUsage } from './TenantUsage'

/** Minimal platform admin UI (slice 0.6/0.7): sign-in with mandatory 2FA and the tenant list.
 *  Talks to the separate admin API (/admin-api, its own cookie and database role). */
export function AdminPage() {
  const { t } = useTranslation()
  const client = useQueryClient()
  const session = useQuery({
    queryKey: ['admin-session'],
    queryFn: async () => {
      try {
        const s = await request<AdminSessionOut>('GET', '/admin-api/auth/session')
        setCsrfToken(s.csrf_token)
        return s
      } catch (error) {
        if (error instanceof ApiError && error.status === 401) return null
        throw error
      }
    },
  })
  const onSession = (s: AdminSessionOut) => {
    setCsrfToken(s.csrf_token)
    client.setQueryData(['admin-session'], s)
  }
  const ready = session.data?.mfa_state === 'ok'

  return (
    <div className="min-h-screen bg-ground px-4 py-6 sm:px-8">
      <header className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <Logo />
          <span className="font-display text-lg font-bold">{t('admin.title')}</span>
        </div>
        <div className="flex items-center gap-3">
          <LanguageSwitch />
          <AppearanceMenu />
        </div>
      </header>
      {session.isPending ? null : ready ? (
        <Tenants />
      ) : (
        <AdminSignIn state={session.data?.mfa_state} onSession={onSession} />
      )}
    </div>
  )
}

function AdminSignIn({
  state,
  onSession,
}: {
  state: string | undefined
  onSession: (s: AdminSessionOut) => void
}) {
  const { t } = useTranslation()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [code, setCode] = useState('')
  const login = useMutation({
    mutationFn: () =>
      request<AdminSessionOut>('POST', '/admin-api/auth/login', { email, password }),
    onSuccess: onSession,
  })
  const setup = useMutation({
    mutationFn: () =>
      request<{ secret: string; otpauth_uri: string }>('POST', '/admin-api/auth/mfa/setup'),
  })
  const finish = useMutation({
    mutationFn: () =>
      request<AdminSessionOut>(
        'POST',
        state === 'enroll' ? '/admin-api/auth/mfa/confirm' : '/admin-api/auth/mfa/verify',
        { code },
      ),
    onSuccess: onSession,
  })
  const error = login.error ?? setup.error ?? finish.error

  return (
    <Card className="mx-auto flex max-w-sm flex-col gap-4">
      <h1 className="font-display text-2xl font-bold">{t('auth.signIn')}</h1>
      {error ? <Alert>{errorMessage(error, t)}</Alert> : null}
      {!state ? (
        <form
          className="flex flex-col gap-4"
          onSubmit={(e) => {
            e.preventDefault()
            login.mutate()
          }}
        >
          <Field
            label={t('auth.email')}
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
          <Field
            label={t('auth.password')}
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          <Button type="submit" disabled={login.isPending}>
            {t('auth.continue')}
          </Button>
        </form>
      ) : (
        <form
          className="flex flex-col gap-4"
          onSubmit={(e) => {
            e.preventDefault()
            finish.mutate()
          }}
        >
          {state === 'enroll' &&
            (setup.data ? (
              <code className="rounded-lg bg-ground p-3 font-mono tracking-widest break-all">
                {setup.data.secret}
              </code>
            ) : (
              <Button type="button" variant="ghost" onClick={() => setup.mutate()}>
                {t('auth.startEnroll')}
              </Button>
            ))}
          <Field
            label={t('auth.code')}
            inputMode="numeric"
            value={code}
            onChange={(e) => setCode(e.target.value)}
          />
          <Button type="submit" disabled={finish.isPending}>
            {t('auth.verify')}
          </Button>
        </form>
      )}
    </Card>
  )
}

function Tenants() {
  const { t } = useTranslation()
  const [open, setOpen] = useState<string>()
  const tenants = useQuery({
    queryKey: ['admin-tenants'],
    queryFn: () => request<TenantOut[]>('GET', '/admin-api/tenants'),
  })
  return (
    <Card className="overflow-hidden p-0">
      <h1 className="px-5 pt-5 font-display text-xl font-bold">{t('admin.businesses')}</h1>
      {tenants.error && <Alert>{errorMessage(tenants.error, t)}</Alert>}
      {tenants.data?.length === 0 && <p className="px-5 py-4 text-ink-soft">{t('admin.none')}</p>}
      <div className="overflow-x-auto">
        <table className="w-full min-w-[640px] border-collapse text-sm">
          <thead>
            <tr className="text-left text-xs tracking-wider text-muted uppercase">
              <th className="px-5 py-3">{t('admin.name')}</th>
              <th className="px-3 py-3">{t('admin.profile')}</th>
              <th className="px-3 py-3">{t('admin.subscription')}</th>
              <th className="px-3 py-3">{t('admin.modules')}</th>
              <th className="px-5 py-3">{t('admin.status')}</th>
            </tr>
          </thead>
          <tbody>
            {tenants.data?.map((tenant) => {
              const state = tenant.subscription_state ?? 'unknown'
              return (
                <tr key={tenant.id} className="border-t border-line">
                  <td className="px-5 py-3.5 font-bold">
                    <button type="button" className="underline" onClick={() => setOpen(tenant.id)}>
                      {tenant.name}
                    </button>
                  </td>
                  <td className="px-3 py-3.5 text-ink-soft">{t(`profiles.${tenant.profile}`)}</td>
                  <td className="px-3 py-3.5">
                    <StateBadge state={state} label={t(`states.${state}`)} />
                  </td>
                  <td className="px-3 py-3.5 text-ink-soft">{tenant.modules.length}</td>
                  <td className="px-5 py-3.5 text-ink-soft">{tenant.status}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      {open && (
        <div className="flex flex-col gap-4 p-5">
          <TenantUsage key={open} tenantId={open} />
          <TenantOps key={`ops-${open}`} tenantId={open} />
        </div>
      )}
    </Card>
  )
}
