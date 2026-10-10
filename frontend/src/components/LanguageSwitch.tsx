import { clsx } from 'clsx'
import { useTranslation } from 'react-i18next'

import { LANGUAGES, setLanguage } from '../lib/i18n'

export function LanguageSwitch() {
  const { t, i18n } = useTranslation()
  return (
    <div
      role="group"
      aria-label={t('lang.label')}
      className="flex overflow-hidden rounded-full border border-line-strong text-sm font-bold"
    >
      {LANGUAGES.map((code) => (
        <button
          key={code}
          type="button"
          aria-pressed={i18n.language === code}
          onClick={() => setLanguage(code)}
          className={clsx(
            'min-h-9 px-3.5',
            i18n.language === code ? 'bg-ink text-ground' : 'text-ink-soft',
          )}
        >
          {t(`lang.${code}`)}
        </button>
      ))}
    </div>
  )
}
