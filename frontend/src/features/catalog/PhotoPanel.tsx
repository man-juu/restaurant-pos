import { useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Alert, Button, Card } from '../../components/ui'
import type { ItemOut } from '../../lib/api/types'
import { errorMessage } from '../../lib/errors'
import { AiImagePanel } from './AiImagePanel'
import { MAX_PHOTO_BYTES, usePhoto } from './api'

const ACCEPT = 'image/jpeg,image/png,image/webp'

/** FR-CAT-001: optional item photo. The server checks and re-encodes every file. */
export function PhotoPanel({ item, canEdit }: { item: ItemOut; canEdit: boolean }) {
  const { t } = useTranslation()
  return (
    <Card className="flex flex-col gap-3">
      <div>
        <h2 className="font-display text-lg font-bold">{t('catalog.photo.title')}</h2>
        <p className="text-sm text-muted">{t('catalog.photo.optional')}</p>
      </div>
      {canEdit ? <PhotoEditor item={item} /> : <PhotoView item={item} />}
      {canEdit && <AiImagePanel itemId={item.id} />}
    </Card>
  )
}

function PhotoView({ item }: { item: ItemOut }) {
  const { t } = useTranslation()
  if (!item.photo_upload_id)
    return (
      <div className="grid h-32 w-32 place-items-center rounded-xl border border-dashed border-line-strong text-center text-sm text-muted">
        {t('catalog.photo.none')}
      </div>
    )
  return (
    <img
      src={`/api/v1/uploads/${item.photo_upload_id}`}
      alt={t('catalog.photo.alt', { name: item.name })}
      className="h-32 w-32 rounded-xl border border-line object-cover"
    />
  )
}

function PhotoEditor({ item }: { item: ItemOut }) {
  const { t, i18n } = useTranslation()
  const { upload, remove } = usePhoto(item.id, i18n.language)
  const input = useRef<HTMLInputElement>(null)
  const [tooBig, setTooBig] = useState(false)
  const busy = upload.isPending || remove.isPending
  const error = upload.error ?? remove.error
  const label = item.photo_upload_id ? t('catalog.photo.replace') : t('catalog.photo.choose')

  const onFile = (file: File | undefined) => {
    if (!file) return
    // Checked here too so a big file fails at once instead of after a slow upload.
    setTooBig(file.size > MAX_PHOTO_BYTES)
    if (file.size <= MAX_PHOTO_BYTES) upload.mutate(file)
  }

  return (
    <>
      {tooBig && <Alert>{t('catalog.photo.tooBig')}</Alert>}
      {error ? <Alert>{errorMessage(error, t)}</Alert> : null}
      <div className="flex flex-wrap items-center gap-4">
        <PhotoView item={item} />
        <div className="flex flex-wrap gap-2">
          <input
            ref={input}
            type="file"
            accept={ACCEPT}
            className="sr-only"
            aria-label={t('catalog.photo.choose')}
            onChange={(e) => {
              onFile(e.target.files?.[0])
              e.target.value = '' // allow choosing the same file again after an error
            }}
          />
          <Button onClick={() => input.current?.click()} disabled={busy} aria-busy={busy}>
            {upload.isPending ? t('catalog.photo.uploading') : label}
          </Button>
          {item.photo_upload_id && (
            <Button variant="ghost" onClick={() => remove.mutate()} disabled={busy}>
              {t('catalog.photo.remove')}
            </Button>
          )}
        </div>
      </div>
    </>
  )
}
