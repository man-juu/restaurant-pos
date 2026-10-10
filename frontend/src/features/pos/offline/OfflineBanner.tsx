import { useTranslation } from 'react-i18next'

import { CheckInput } from '../../../components/form'
import { Button } from '../../../components/ui'
import type { OfflineState } from './useOffline'

/** Connection state, orders still waiting to upload, and the ones the server turned away. */
export function OfflineBanner({
  offline,
  working,
  setWorking,
}: {
  offline: OfflineState
  working: boolean
  setWorking: (on: boolean) => void
}) {
  const { t } = useTranslation()
  const { queue } = offline
  return (
    <div
      role="status"
      className="flex flex-wrap items-center gap-3 rounded-xl border border-line-strong p-3 text-sm"
    >
      <span className="font-semibold">
        {offline.online ? t('pos.offline.online') : t('pos.offline.noConnection')}
      </span>
      {offline.online && (
        <CheckInput label={t('pos.offline.workOffline')} checked={working} onChange={setWorking} />
      )}
      <span>{t('pos.offline.pending', { count: queue.pending.length })}</span>
      {queue.pending.length > 0 && offline.online && (
        <Button variant="ghost" disabled={offline.syncing} onClick={() => void offline.sync()}>
          {t('pos.offline.syncNow')}
        </Button>
      )}
      {(queue.failed.length > 0 || queue.problems.length > 0) && (
        <>
          <span>
            {t('pos.offline.needsLook', { count: queue.failed.length + queue.problems.length })}
          </span>
          <ul className="w-full list-disc pl-5">
            {queue.failed.map((f) => (
              <li key={f.body.client_id}>{t('pos.offline.refused', { code: f.code })}</li>
            ))}
            {queue.problems.map((p) => (
              <li key={p.client_id}>
                {t('pos.offline.leftOpen', { number: p.number, problem: p.problem })}
              </li>
            ))}
          </ul>
          <Button variant="ghost" onClick={offline.clear}>
            {t('pos.offline.dismiss')}
          </Button>
        </>
      )}
    </div>
  )
}
