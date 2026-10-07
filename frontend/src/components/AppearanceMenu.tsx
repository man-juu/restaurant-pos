import * as Popover from '@radix-ui/react-dialog'
import { clsx } from 'clsx'
import { useTranslation } from 'react-i18next'

import { ACCENTS, BACKGROUNDS, MODES, setAppearance, useAppearance } from '../lib/theme'

/** Theme mode, accent swatch and background picker (per device). */
export function AppearanceMenu() {
  const { t } = useTranslation()
  const appearance = useAppearance()
  return (
    <Popover.Root>
      <Popover.Trigger
        aria-label={t('appearance.open')}
        className="flex h-11 w-11 items-center justify-center rounded-xl border border-line-strong bg-card text-ink"
      >
        <svg
          width="18"
          height="18"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          aria-hidden="true"
        >
          <circle cx="12" cy="12" r="9" />
          <path d="M12 3a9 9 0 0 0 0 18z" fill="currentColor" />
        </svg>
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Overlay className="fixed inset-0 bg-black/40" />
        <Popover.Content className="fixed top-1/2 left-1/2 flex w-[min(92vw,420px)] -translate-x-1/2 -translate-y-1/2 flex-col gap-5 rounded-2xl border border-line-strong bg-card p-5 text-ink shadow-2xl">
          <Popover.Title className="font-display text-lg font-bold">
            {t('appearance.title')}
          </Popover.Title>
          <Popover.Description className="sr-only">
            {t('appearance.description')}
          </Popover.Description>

          <fieldset className="flex flex-col gap-2">
            <legend className="mb-2 text-sm font-semibold text-ink-soft">
              {t('appearance.mode')}
            </legend>
            <div className="grid grid-cols-3 gap-2">
              {MODES.map((mode) => (
                <button
                  key={mode}
                  type="button"
                  aria-pressed={appearance.mode === mode}
                  onClick={() => setAppearance({ mode })}
                  className={clsx(
                    'min-h-11 rounded-xl border text-sm font-bold',
                    appearance.mode === mode
                      ? 'border-accent bg-raised text-ink'
                      : 'border-line-strong text-ink-soft',
                  )}
                >
                  {t(`appearance.modes.${mode}`)}
                </button>
              ))}
            </div>
          </fieldset>

          <fieldset className="flex flex-col gap-2">
            <legend className="mb-2 text-sm font-semibold text-ink-soft">
              {t('appearance.accent')}
            </legend>
            <div className="flex flex-wrap gap-3">
              {ACCENTS.map((accent) => (
                <button
                  key={accent}
                  type="button"
                  aria-pressed={appearance.accent === accent}
                  aria-label={t(`appearance.accents.${accent}`)}
                  title={t(`appearance.accents.${accent}`)}
                  onClick={() => setAppearance({ accent })}
                  data-accent={accent}
                  className={clsx(
                    'h-11 w-11 rounded-full border-2 bg-accent',
                    appearance.accent === accent ? 'border-ink' : 'border-transparent',
                  )}
                />
              ))}
            </div>
          </fieldset>

          <fieldset className="flex flex-col gap-2">
            <legend className="mb-2 text-sm font-semibold text-ink-soft">
              {t('appearance.background')}
            </legend>
            <div className="grid grid-cols-4 gap-2">
              {BACKGROUNDS.map((background) => (
                <button
                  key={background}
                  type="button"
                  aria-pressed={appearance.background === background}
                  aria-label={t(`appearance.backgrounds.${background}`)}
                  onClick={() => setAppearance({ background })}
                  className={clsx(
                    'aspect-[4/3] rounded-xl border-2 bg-cover bg-center',
                    appearance.background === background ? 'border-accent' : 'border-line',
                  )}
                  style={{ backgroundImage: `url('/backgrounds/${background}.svg')` }}
                />
              ))}
            </div>
          </fieldset>

          <Popover.Close className="min-h-11 rounded-xl bg-accent font-display text-sm font-extrabold text-on-accent">
            {t('appearance.done')}
          </Popover.Close>
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  )
}
