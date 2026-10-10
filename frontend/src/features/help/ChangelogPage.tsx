import { useEffect } from 'react'
import { useTranslation } from 'react-i18next'

import { Card } from '../../components/ui'
import { formatDate, intlLocale } from '../../lib/format'
import { CHANGELOG, markSeen } from './changelog'

/** FR-X-007: the in-app changelog. */
export function ChangelogPage() {
  const { t, i18n } = useTranslation()
  useEffect(markSeen, [])
  return (
    <div className="flex flex-col gap-5">
      <h1 className="font-display text-3xl font-extrabold">{t('changelog.title')}</h1>
      {CHANGELOG.map((e) => (
        <Card key={e.id} className="flex flex-col gap-2">
          <h2 className="font-bold">{formatDate(e.date, intlLocale(i18n.language))}</h2>
          <ul className="list-disc pl-5 text-sm">
            {(t(`changelog.items.${e.id}`, { returnObjects: true }) as string[]).map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        </Card>
      ))}
    </div>
  )
}
