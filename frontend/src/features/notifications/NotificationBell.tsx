import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'

import { useUnread } from './api'

/** FR-NTF-001: unread count in the header; opens the notification center. */
export function NotificationBell() {
  const { t } = useTranslation()
  const unread = useUnread().data?.unread ?? 0
  const label = t('notifications.bell', { count: unread })
  return (
    <Link
      to="/notifications"
      aria-label={label}
      title={label}
      className="relative inline-flex min-h-11 min-w-11 items-center justify-center rounded-lg hover:bg-raised"
    >
      <svg
        aria-hidden="true"
        viewBox="0 0 24 24"
        className="size-5"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
      >
        <path d="M6 8a6 6 0 1 1 12 0c0 7 3 9 3 9H3s3-2 3-9" />
        <path d="M10.3 21a1.94 1.94 0 0 0 3.4 0" />
      </svg>
      {unread > 0 && (
        <span className="absolute right-1 top-1 min-w-5 rounded-full bg-danger px-1 text-center text-xs font-bold text-white">
          {unread > 99 ? '99+' : unread}
        </span>
      )}
    </Link>
  )
}
