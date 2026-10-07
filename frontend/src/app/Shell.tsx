import * as DropdownMenu from '@radix-ui/react-dropdown-menu'
import { clsx } from 'clsx'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { NavLink, Navigate, Outlet } from 'react-router'

import { InstallPrompt } from '../components/InstallPrompt'
import { AppearanceMenu } from '../components/AppearanceMenu'
import { LanguageSwitch } from '../components/LanguageSwitch'
import { Button, Logo } from '../components/ui'
import type { Capabilities, SessionInfo } from '../lib/api/types'
import { type NavItem, navItems } from './nav'
import { useCapabilities, useLogout, useSession, useSwitchTenant } from '../lib/session'

export function Shell() {
  const session = useSession()
  const caps = useCapabilities(Boolean(session.data?.active_tenant_id))
  if (session.isPending) return null
  if (!session.data || session.data.mfa_state !== 'ok') return <Navigate to="/login" replace />
  const items = navItems(caps.data)

  return (
    <div className="flex min-h-screen flex-wrap bg-ground pb-20 md:pb-0">
      <SideNav items={items} />
      <main className="flex min-w-0 flex-[999_1_560px] flex-col gap-6 px-4 py-5 sm:px-8">
        <SubscriptionBanner caps={caps.data} />
        <TopBar session={session.data} />
        <InstallPrompt />
        <Outlet context={{ session: session.data, caps: caps.data }} />
      </main>
      <BottomNav items={items} />
    </div>
  )
}

function SideNav({ items }: { items: NavItem[] }) {
  const { t } = useTranslation()
  return (
    <nav
      aria-label={t('nav.main')}
      className="hidden max-w-64 flex-[1_1_232px] flex-col gap-1.5 border-r border-line bg-panel px-4 py-6 md:flex"
    >
      <div className="flex items-center gap-2.5 px-2 pb-5">
        <Logo />
        <span className="font-display text-lg font-bold">{t('app.title')}</span>
      </div>
      {items.map((item) => (
        <NavLink
          key={item.key}
          to={item.to}
          end
          className={({ isActive }) =>
            clsx(
              'flex min-h-11 items-center rounded-xl px-3 font-semibold',
              isActive ? 'bg-raised text-ink' : 'text-ink-soft hover:bg-card',
            )
          }
        >
          {t(`nav.${item.key}`)}
        </NavLink>
      ))}
    </nav>
  )
}

function BottomNav({ items }: { items: NavItem[] }) {
  const { t } = useTranslation()
  return (
    <nav
      aria-label={t('nav.main')}
      className="fixed inset-x-0 bottom-0 grid border-t border-line bg-panel px-2 pt-2 pb-4 md:hidden"
      style={{ gridTemplateColumns: `repeat(${Math.min(items.length, 5)}, minmax(0, 1fr))` }}
    >
      {items.slice(0, 5).map((item) => (
        <NavLink
          key={item.key}
          to={item.to}
          end
          className={({ isActive }) =>
            clsx(
              'flex min-h-12 items-center justify-center text-center text-xs font-bold',
              isActive ? 'text-accent' : 'text-ink-soft',
            )
          }
        >
          {t(`nav.${item.key}`)}
        </NavLink>
      ))}
    </nav>
  )
}

function TopBar({ session }: { session: SessionInfo }) {
  const { t } = useTranslation()
  const logout = useLogout()
  const switchTenant = useSwitchTenant()
  const active = session.tenants.find((tenant) => tenant.id === session.active_tenant_id)
  return (
    <header className="flex flex-wrap items-center justify-between gap-3">
      <DropdownMenu.Root>
        <DropdownMenu.Trigger asChild>
          <Button variant="ghost" aria-label={t('shell.switchBusiness')}>
            <span className="h-5 w-5 rounded-md bg-accent" />
            {active?.name ?? t('shell.business')}
          </Button>
        </DropdownMenu.Trigger>
        <DropdownMenu.Portal>
          <DropdownMenu.Content
            sideOffset={6}
            className="min-w-56 rounded-xl border border-line-strong bg-card p-1.5 text-ink shadow-xl"
          >
            {session.tenants.map((tenant) => (
              <DropdownMenu.Item
                key={tenant.id}
                onSelect={() => switchTenant.mutate({ tenant_id: tenant.id })}
                className="flex min-h-11 cursor-pointer items-center rounded-lg px-3 outline-none data-[highlighted]:bg-raised"
              >
                {tenant.name}
              </DropdownMenu.Item>
            ))}
          </DropdownMenu.Content>
        </DropdownMenu.Portal>
      </DropdownMenu.Root>
      <div className="flex items-center gap-3">
        <LanguageSwitch />
        <AppearanceMenu />
        <Button variant="ghost" onClick={() => logout.mutate()}>
          {t('auth.signOut')}
        </Button>
      </div>
    </header>
  )
}

const BANNER_STATES = new Set(['expiring', 'grace', 'read_only'])

/** FR-SUB-002: shown to owners and co-owners (days_left is only sent to them). */
export function SubscriptionBanner({ caps }: { caps: Capabilities | undefined }) {
  const { t } = useTranslation()
  const [dismissed, setDismissed] = useState(false)
  const state = caps?.subscription.state
  if (!caps || !state || !BANNER_STATES.has(state) || dismissed) return null
  if (state === 'expiring' && caps.subscription.days_left == null) return null
  return (
    <div
      role="status"
      className="flex flex-wrap items-center gap-3 rounded-2xl border border-notice-line bg-notice px-4 py-3"
    >
      <p className="flex-1 text-sm">
        {t(`subscription.${state}`, { count: caps.subscription.days_left ?? 0 })}
      </p>
      {state === 'expiring' && (
        <Button variant="ghost" onClick={() => setDismissed(true)}>
          {t('subscription.dismiss')}
        </Button>
      )}
    </div>
  )
}
