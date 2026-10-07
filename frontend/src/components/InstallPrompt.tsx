import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Button } from './ui'

interface BeforeInstallPromptEvent extends Event {
  prompt: () => Promise<void>
}

/** "Install the app" card (PWA). Shown only when the browser offers installation. */
export function InstallPrompt() {
  const { t } = useTranslation()
  const [event, setEvent] = useState<BeforeInstallPromptEvent | null>(null)

  useEffect(() => {
    const onPrompt = (e: Event) => {
      e.preventDefault() // keep the event so our own button can trigger the prompt
      setEvent(e as BeforeInstallPromptEvent)
    }
    window.addEventListener('beforeinstallprompt', onPrompt)
    return () => window.removeEventListener('beforeinstallprompt', onPrompt)
  }, [])

  if (!event) return null
  return (
    <div className="flex items-center gap-3 rounded-2xl border border-[#4a2e1d] bg-gradient-to-br from-[#2a1a12] to-card p-4">
      <div className="flex-1">
        <p className="font-extrabold">{t('install.title')}</p>
        <p className="text-sm text-ink-soft">{t('install.body')}</p>
      </div>
      <Button
        onClick={() => {
          void event.prompt()
          setEvent(null)
        }}
      >
        {t('install.action')}
      </Button>
    </div>
  )
}
