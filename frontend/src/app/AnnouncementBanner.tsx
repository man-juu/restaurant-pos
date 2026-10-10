import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'

import { Button } from '../components/ui'
import { request } from '../lib/api/client'

interface Announcement {
  id: string
  level: 'info' | 'warning'
  title: string
  body: string
}

/** FR-ADM-005: platform news for this business, until each person dismisses it. */
export function AnnouncementBanner() {
  const { t, i18n } = useTranslation()
  const client = useQueryClient()
  const lang = i18n.language.slice(0, 2)
  const list = useQuery({
    queryKey: ['announcements', lang],
    queryFn: () => request<Announcement[]>('GET', `/api/v1/announcements?lang=${lang}`),
    staleTime: 5 * 60_000,
  })
  const dismiss = useMutation({
    mutationFn: (id: string) => request<void>('POST', `/api/v1/announcements/${id}/dismiss`),
    onSuccess: () => client.invalidateQueries({ queryKey: ['announcements'] }),
  })
  return (
    <>
      {list.data?.map((a) => (
        <section
          key={a.id}
          aria-label={a.title}
          className={`flex flex-wrap items-start justify-between gap-3 rounded-xl border p-3 ${
            a.level === 'warning' ? 'border-warn bg-warn-surface' : 'border-notice-line bg-notice'
          }`}
        >
          <div>
            <p className="font-bold">{a.title}</p>
            <p className="text-sm whitespace-pre-line">{a.body}</p>
          </div>
          <Button variant="ghost" onClick={() => dismiss.mutate(a.id)}>
            {t('announcements.dismiss')}
          </Button>
        </section>
      ))}
    </>
  )
}
