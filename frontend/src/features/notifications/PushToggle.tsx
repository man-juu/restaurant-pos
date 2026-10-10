import { useQuery } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Alert, Button } from '../../components/ui'
import { request } from '../../lib/api/client'

interface PushKey {
  enabled: boolean
  public_key: string | null
}

const supported = () =>
  typeof navigator !== 'undefined' && 'serviceWorker' in navigator && 'PushManager' in window

function keyBytes(base64url: string): Uint8Array {
  const b64 = base64url.replace(/-/g, '+').replace(/_/g, '/')
  const raw = atob(b64 + '='.repeat((4 - (b64.length % 4)) % 4))
  return Uint8Array.from(raw, (c) => c.charCodeAt(0))
}

async function current(): Promise<PushSubscription | null> {
  const reg = await navigator.serviceWorker.ready
  return reg.pushManager.getSubscription()
}

/** FR-NTF-005: allow or stop notifications on this phone or computer (installed app). */
export function PushToggle() {
  const { t } = useTranslation()
  const key = useQuery({
    queryKey: ['push-key'],
    queryFn: () => request<PushKey>('GET', '/api/v1/push/key'),
    enabled: supported(),
  })
  const [on, setOn] = useState<boolean>()
  const [error, setError] = useState(false)
  useEffect(() => {
    if (supported())
      void current().then(
        (s) => setOn(Boolean(s)),
        () => setOn(false),
      )
  }, [])
  if (!supported() || !key.data?.enabled || !key.data.public_key || on === undefined) return null
  const publicKey = key.data.public_key
  const turnOn = async () => {
    setError(false)
    try {
      if ((await Notification.requestPermission()) !== 'granted') throw new Error('denied')
      const reg = await navigator.serviceWorker.ready
      const sub = await reg.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: keyBytes(publicKey) as BufferSource,
      })
      await request('PUT', '/api/v1/push/subscription', sub.toJSON())
      setOn(true)
    } catch {
      setError(true)
    }
  }
  const turnOff = async () => {
    const sub = await current()
    if (sub) {
      await request('POST', '/api/v1/push/subscription/delete', { endpoint: sub.endpoint })
      await sub.unsubscribe()
    }
    setOn(false)
  }
  return (
    <div className="flex flex-col gap-2">
      <Button
        variant="ghost"
        className="self-start"
        onClick={() => void (on ? turnOff() : turnOn())}
      >
        {t(on ? 'push.off' : 'push.on')}
      </Button>
      {error && <Alert>{t('push.failed')}</Alert>}
    </div>
  )
}
