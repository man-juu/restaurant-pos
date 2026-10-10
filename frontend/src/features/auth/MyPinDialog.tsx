import * as Dialog from '@radix-ui/react-dialog'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Alert, Button, Field } from '../../components/ui'
import { ApiError, request } from '../../lib/api/client'
import { errorMessage } from '../../lib/errors'

const PIN = /^\d{4,6}$/

/** FR-IDN-004: set my PIN (with my password) and allow it on this device if it is one. */
function useSetPin() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: async (body: { pin: string; password: string }) => {
      await request<void>('PUT', '/api/v1/me/pin', body)
      try {
        await request<void>('POST', '/api/v1/devices/this/enrol')
      } catch (err) {
        // Not a registered device: the PIN works on registered tills after a full sign-in.
        if (!(err instanceof ApiError && err.status === 404)) throw err
      }
    },
    onSuccess: () => client.invalidateQueries({ queryKey: ['this-device'] }),
  })
}

export function MyPinDialog() {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const [pin, setPin] = useState('')
  const [password, setPassword] = useState('')
  const save = useSetPin()
  return (
    <Dialog.Root open={open} onOpenChange={setOpen}>
      <Dialog.Trigger asChild>
        <Button variant="ghost">{t('pin.mine')}</Button>
      </Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 bg-black/40" />
        <Dialog.Content className="fixed top-1/2 left-1/2 flex w-[min(92vw,400px)] -translate-x-1/2 -translate-y-1/2 flex-col gap-4 rounded-2xl border border-line-strong bg-card p-5 text-ink shadow-2xl">
          <Dialog.Title className="font-display text-xl font-bold">{t('pin.mine')}</Dialog.Title>
          <Dialog.Description className="text-sm text-ink-soft">{t('pin.help')}</Dialog.Description>
          <Field
            label={t('pin.new')}
            type="password"
            inputMode="numeric"
            autoComplete="off"
            maxLength={6}
            value={pin}
            onChange={(e) => setPin(e.target.value)}
          />
          <Field
            label={t('auth.password')}
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          {save.error ? <Alert>{errorMessage(save.error, t)}</Alert> : null}
          {save.isSuccess && (
            <p role="status" className="text-sm text-good">
              {t('pin.saved')}
            </p>
          )}
          <Button
            disabled={!PIN.test(pin) || !password || save.isPending}
            onClick={() =>
              save.mutate({ pin, password }, { onSuccess: () => (setPin(''), setPassword('')) })
            }
          >
            {t('pin.save')}
          </Button>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
