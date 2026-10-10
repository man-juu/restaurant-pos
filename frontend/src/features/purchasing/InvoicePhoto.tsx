import { useTranslation } from 'react-i18next'

import { Alert } from '../../components/ui'
import { errorMessage } from '../../lib/errors'
import { useUploadInvoice } from './api'

/** FR-PUR-011: optional photo of the supplier invoice (required only if the owner says so). */
export function InvoicePhoto({ onUploaded }: { onUploaded: (id: string | undefined) => void }) {
  const { t } = useTranslation()
  const upload = useUploadInvoice()
  return (
    <div className="flex flex-col gap-2">
      <label className="flex flex-col gap-1 text-sm font-semibold text-ink-soft">
        {t('purchasing.quick.invoice')}
        <input
          type="file"
          accept="image/jpeg,image/png,image/webp"
          capture="environment"
          onChange={(e) => {
            const file = e.target.files?.[0]
            onUploaded(undefined)
            if (file) upload.mutate(file, { onSuccess: (ref) => onUploaded(ref.id) })
          }}
        />
      </label>
      {upload.isPending && <p className="text-sm text-muted">{t('catalog.photo.uploading')}</p>}
      {upload.isSuccess && <p className="text-sm text-good">{t('purchasing.quick.invoiceOk')}</p>}
      {upload.error ? <Alert>{errorMessage(upload.error, t)}</Alert> : null}
    </div>
  )
}
