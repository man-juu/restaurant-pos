import * as Dialog from '@radix-ui/react-dialog'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useLocation } from 'react-router'

import { Button } from '../../components/ui'
import { seenLatest } from './changelog'

const PAGES = new Set([
  'home',
  'pos',
  'tables',
  'kitchen',
  'catalog',
  'inventory',
  'purchasing',
  'production',
  'transfers',
  'sales',
  'finance',
  'reports',
  'settings',
  'notifications',
])

/** FR-X-007: short help for the page you are on, and the way to "What's new". */
export function HelpDialog() {
  const { t } = useTranslation()
  const { pathname } = useLocation()
  const [open, setOpen] = useState(false)
  const first = pathname.split('/')[1] || 'home'
  const page = PAGES.has(first) ? first : 'home'
  const fresh = !seenLatest()
  return (
    <Dialog.Root open={open} onOpenChange={setOpen}>
      <Dialog.Trigger asChild>
        <Button variant="ghost" aria-label={t('help.open')}>
          {t('help.mark')}
          {fresh && (
            <span className="ml-1 inline-block h-2 w-2 rounded-full bg-accent" aria-hidden="true" />
          )}
        </Button>
      </Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 bg-black/40" />
        <Dialog.Content className="fixed top-1/2 left-1/2 flex max-h-[85vh] w-[min(92vw,480px)] -translate-x-1/2 -translate-y-1/2 flex-col gap-3 overflow-y-auto rounded-2xl border border-line-strong bg-card p-5 text-ink shadow-2xl">
          <Dialog.Title className="font-display text-xl font-bold">
            {t(`help.pages.${page}.title`)}
          </Dialog.Title>
          <Dialog.Description className="text-sm whitespace-pre-line text-ink-soft">
            {t(`help.pages.${page}.body`)}
          </Dialog.Description>
          <Link
            to="/changelog"
            onClick={() => setOpen(false)}
            className="text-sm font-semibold text-accent underline"
          >
            {t(fresh ? 'help.newChanges' : 'help.changelog')}
          </Link>
          <Dialog.Close asChild>
            <Button className="self-end">{t('help.close')}</Button>
          </Dialog.Close>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
