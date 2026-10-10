import { useTranslation } from 'react-i18next'
import { Alert, Button } from '../../components/ui'
import { errorMessage } from '../../lib/errors'

export function SaveBar({
  mutation,
  onSave,
  disabled,
}: {
  mutation: { isPending: boolean; isSuccess: boolean; error: unknown }
  onSave: () => void
  disabled?: boolean
}) {
  const { t } = useTranslation()
  return (
    <div className="flex flex-wrap items-center gap-3">
      <Button
        onClick={onSave}
        disabled={disabled || mutation.isPending}
        aria-busy={mutation.isPending}
      >
        {mutation.isPending ? t('auth.working') : t('settings.save')}
      </Button>
      {mutation.isSuccess && (
        <span role="status" className="text-sm text-good">
          {t('settings.saved')}
        </span>
      )}
      {mutation.error ? <Alert>{errorMessage(mutation.error, t)}</Alert> : null}
    </div>
  )
}

export const inputClass = 'min-h-11 rounded-lg border border-line-strong bg-ground px-3 text-ink'
