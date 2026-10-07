import { useTranslation } from 'react-i18next'
import { useOutletContext } from 'react-router'

import { Card } from '../../components/ui'
import type { Capabilities, SessionInfo } from '../../lib/api/types'

const TILES = ['netSales', 'orders', 'foodCost', 'stockValue'] as const

export function DashboardPage() {
  const { t } = useTranslation()
  const { session } = useOutletContext<{ session: SessionInfo; caps?: Capabilities }>()
  return (
    <div className="flex flex-col gap-6">
      <h1 className="font-display text-3xl font-extrabold tracking-tight">
        {t('dashboard.greeting', { name: session.user.name })}
      </h1>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {TILES.map((tile) => (
          <Card key={tile}>
            <p className="text-sm font-semibold text-muted">{t(`dashboard.${tile}`)}</p>
            <p className="mt-2 font-display text-2xl font-extrabold text-ink-soft">
              {t('dashboard.noData')}
            </p>
          </Card>
        ))}
      </div>
      <Card>
        <p className="text-ink-soft">{t('dashboard.empty')}</p>
      </Card>
    </div>
  )
}
