import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'

import { Alert, Button, Card } from '../../components/ui'
import type { NotificationOut } from '../../lib/api/types'
import { errorMessage } from '../../lib/errors'
import { useMarkRead, useNotifications } from './api'

/** FR-NTF-001: this user's alerts, newest unread first. */
export function NotificationsPage() {
  const { t } = useTranslation()
  const list = useNotifications()
  const mark = useMarkRead()
  const unread = list.data?.some((n) => !n.read_at)
  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="font-display text-3xl font-extrabold">{t('notifications.title')}</h1>
        {unread && (
          <Button variant="ghost" onClick={() => mark.mutate(undefined)}>
            {t('notifications.readAll')}
          </Button>
        )}
      </div>
      {list.error && <Alert>{errorMessage(list.error, t)}</Alert>}
      {list.isSuccess && list.data.length === 0 && (
        <p className="text-ink-soft">{t('notifications.empty')}</p>
      )}
      <ul className="flex flex-col gap-2">
        {list.data?.map((n) => (
          <Item key={n.id} n={n} onOpen={() => !n.read_at && mark.mutate(n.id)} />
        ))}
      </ul>
    </div>
  )
}

function Item({ n, onOpen }: { n: NotificationOut; onOpen: () => void }) {
  const { t, i18n } = useTranslation()
  const when = new Date(n.created_at).toLocaleString(i18n.language)
  return (
    <li>
      <Card className={n.read_at ? 'opacity-70' : 'border-accent'}>
        <p className="font-semibold">{t(`notifications.kinds.${n.kind}`, n.params)}</p>
        <p className="text-sm text-ink-soft">{when}</p>
        {n.link?.startsWith('/') && (
          <Link
            className="text-sm font-semibold text-accent underline"
            to={n.link}
            onClick={onOpen}
          >
            {t('notifications.open')}
          </Link>
        )}
      </Card>
    </li>
  )
}
