import * as Dialog from '@radix-ui/react-dialog'
import { type ReactNode, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { TextInput } from '../../components/form'
import { Alert, Button } from '../../components/ui'
import { errorMessage } from '../../lib/errors'

/** A small dialog for actions that need a written reason (discount, void, refund). */
export function ReasonDialog({
  title,
  confirm,
  children,
  ready = true,
  pending,
  error,
  onConfirm,
  onClose,
}: {
  title: string
  confirm: string
  children?: ReactNode
  ready?: boolean
  pending: boolean
  error: unknown
  onConfirm: (reason: string) => void
  onClose: () => void
}) {
  const { t } = useTranslation()
  const [reason, setReason] = useState('')
  const ok = ready && reason.trim() !== '' && !pending
  return (
    <Dialog.Root open onOpenChange={(open) => !open && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 bg-black/40" />
        <Dialog.Content className="fixed top-1/2 left-1/2 flex max-h-[92vh] w-[min(94vw,440px)] -translate-x-1/2 -translate-y-1/2 flex-col gap-4 overflow-y-auto rounded-2xl border border-line-strong bg-card p-5 text-ink shadow-2xl">
          <Dialog.Title className="font-display text-xl font-bold">{title}</Dialog.Title>
          <Dialog.Description className="text-sm text-ink-soft">
            {t('pos.reasonHelp')}
          </Dialog.Description>
          {children}
          <TextInput
            label={t('pos.reason')}
            value={reason}
            maxLength={200}
            onChange={(e) => setReason(e.target.value)}
          />
          {error ? <Alert>{errorMessage(error, t)}</Alert> : null}
          <div className="flex flex-wrap gap-2">
            <Button disabled={!ok} aria-busy={pending} onClick={() => onConfirm(reason.trim())}>
              {confirm}
            </Button>
            <Button variant="ghost" onClick={onClose}>
              {t('catalog.cancel')}
            </Button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
