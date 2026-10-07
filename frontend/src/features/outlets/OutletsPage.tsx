import { useTranslation } from 'react-i18next'

import { Alert, Card, StateBadge } from '../../components/ui'
import { errorMessage } from '../../lib/errors'
import { useOutlets } from '../../lib/session'

export function OutletsPage() {
  const { t } = useTranslation()
  const outlets = useOutlets()
  return (
    <div className="flex flex-col gap-4">
      <h1 className="font-display text-3xl font-extrabold">{t('outlets.title')}</h1>
      {outlets.error && <Alert>{errorMessage(outlets.error, t)}</Alert>}
      {outlets.data?.length === 0 && <p className="text-ink-soft">{t('outlets.empty')}</p>}
      <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
        {outlets.data?.map((outlet) => (
          <Card key={outlet.id} className="flex items-center justify-between">
            <div>
              <p className="font-bold">{outlet.name}</p>
              <p className="text-sm text-muted">{outlet.timezone}</p>
            </div>
            <StateBadge
              state={outlet.is_active ? 'active' : 'read_only'}
              label={t(outlet.is_active ? 'outlets.active' : 'outlets.inactive')}
            />
          </Card>
        ))}
      </div>
    </div>
  )
}
