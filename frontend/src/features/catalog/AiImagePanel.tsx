import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Alert, Button } from '../../components/ui'
import type { AiUsage } from '../../lib/api/types'
import { errorMessage } from '../../lib/errors'
import { useAcceptImage, useAiUsage, useGenerateImage } from './aiApi'

/** Free AI image (FR-CAT-013, ADR-022): shown only when the platform has switched it on. */
export function AiImagePanel({ itemId }: { itemId: string }) {
  const usage = useAiUsage()
  if (!usage.data?.enabled) return null
  return <AiImageForm itemId={itemId} usage={usage.data} />
}

function AiImageForm({ itemId, usage }: { itemId: string; usage: AiUsage }) {
  const { t, i18n } = useTranslation()
  const [prompt, setPrompt] = useState('')
  const generate = useGenerateImage()
  const accept = useAcceptImage(itemId)
  const preview = generate.data?.image.id
  const blocked = usage.remaining <= 0
  const resets = new Date(usage.resets_at).toLocaleTimeString(i18n.language, {
    hour: '2-digit',
    minute: '2-digit',
  })

  return (
    <div className="flex flex-col gap-3 border-t border-line pt-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="font-bold">{t('catalog.ai.title')}</h3>
        <span className={blocked ? 'text-sm font-semibold text-warn' : 'text-sm text-muted'}>
          {t('catalog.ai.left', { count: usage.remaining, time: resets })}
        </span>
      </div>
      <p className="text-sm text-muted">{t('catalog.ai.privacy')}</p>
      {generate.error ? <Alert>{errorMessage(generate.error, t)}</Alert> : null}
      {accept.error ? <Alert>{errorMessage(accept.error, t)}</Alert> : null}
      <label className="flex flex-col gap-1 text-sm font-semibold text-ink-soft">
        {t('catalog.ai.prompt')}
        <input
          className="min-h-11 rounded-lg border border-line-strong bg-ground px-3 text-ink"
          value={prompt}
          maxLength={300}
          placeholder={t('catalog.ai.placeholder')}
          onChange={(e) => setPrompt(e.target.value)}
        />
      </label>
      <Button
        onClick={() => generate.mutate(prompt.trim())}
        disabled={blocked || prompt.trim().length < 3 || generate.isPending}
        aria-busy={generate.isPending}
      >
        {generate.isPending ? t('catalog.ai.working') : t('catalog.ai.generate')}
      </Button>
      {preview && !accept.isSuccess && (
        <div className="flex flex-wrap items-center gap-3">
          <img
            src={`/api/v1/uploads/${preview}`}
            alt={t('catalog.ai.previewAlt')}
            className="h-32 w-32 rounded-xl border border-line object-cover"
          />
          <Button onClick={() => accept.mutate(preview)} disabled={accept.isPending}>
            {t('catalog.ai.use')}
          </Button>
          <Button variant="ghost" onClick={() => generate.reset()}>
            {t('catalog.ai.discard')}
          </Button>
        </div>
      )}
    </div>
  )
}
