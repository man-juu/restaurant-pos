import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Alert, Button } from '../../components/ui'
import type { ThisDeviceOut } from '../../lib/api/types'
import { errorMessage } from '../../lib/errors'
import { usePinLogin } from '../../lib/session'

const KEYS = ['1', '2', '3', '4', '5', '6', '7', '8', '9', '', '0', '⌫'] as const

/** FR-IDN-004: on a registered till, pick your name and type your PIN. */
export function PinStep({ device, onPassword }: { device: ThisDeviceOut; onPassword: () => void }) {
  const { t } = useTranslation()
  const [who, setWho] = useState<string>()
  if (!who)
    return (
      <div className="flex flex-col gap-3">
        <p className="text-sm text-ink-soft">{t('pin.device', { name: device.name })}</p>
        <ul className="grid grid-cols-2 gap-2">
          {device.staff.map((s) => (
            <li key={s.user_id}>
              <Button variant="ghost" className="w-full" onClick={() => setWho(s.user_id)}>
                {s.name}
              </Button>
            </li>
          ))}
        </ul>
        <Button variant="ghost" onClick={onPassword}>
          {t('pin.usePassword')}
        </Button>
      </div>
    )
  const name = device.staff.find((s) => s.user_id === who)?.name ?? ''
  return <PinPad userId={who} name={name} onBack={() => setWho(undefined)} />
}

function PinPad({ userId, name, onBack }: { userId: string; name: string; onBack: () => void }) {
  const { t } = useTranslation()
  const login = usePinLogin()
  const [pin, setPin] = useState('')
  const press = (key: string) => {
    if (key === '⌫') return setPin(pin.slice(0, -1))
    if (pin.length < 6) setPin(pin + key)
  }
  return (
    <div className="flex flex-col gap-3">
      <p className="font-bold">{name}</p>
      <p aria-live="polite" className="text-center font-mono text-3xl tracking-[0.5em]">
        {'•'.repeat(pin.length) || ' '}
      </p>
      {login.error ? <Alert>{errorMessage(login.error, t)}</Alert> : null}
      <div className="grid grid-cols-3 gap-2" role="group" aria-label={t('pin.pad')}>
        {KEYS.map((key, i) =>
          key ? (
            <Button
              key={key}
              variant="ghost"
              className="min-h-14 text-xl"
              aria-label={key === '⌫' ? t('pin.delete') : key}
              onClick={() => press(key)}
            >
              {key}
            </Button>
          ) : (
            <span key={`gap-${i}`} />
          ),
        )}
      </div>
      <Button
        disabled={pin.length < 4 || login.isPending}
        onClick={() => login.mutate({ user_id: userId, pin }, { onError: () => setPin('') })}
      >
        {t('pin.signIn')}
      </Button>
      <Button variant="ghost" onClick={onBack}>
        {t('pin.someoneElse')}
      </Button>
    </div>
  )
}
