import { type ReactNode, useState } from 'react'

import { OfflineBanner } from './offline/OfflineBanner'
import { OfflineTill } from './offline/OfflineTill'
import { useOfflinePack, useOfflineQueue } from './offline/useOffline'

/** The till, or its offline twin when the connection is gone or the cashier chose to work
 * offline (FR-SAL-013). Only when the owner left offline selling on (settings, POS). */
export function OfflineSwitch(props: {
  userId: string
  outletId: string
  channelId: string
  currency: string
  children: ReactNode
}) {
  const pack = useOfflinePack(props.channelId).data
  const offline = useOfflineQueue(props.userId)
  const [working, setWorking] = useState(false)
  if (!pack?.enabled) return props.children
  const away = working || !offline.online
  return (
    <>
      <OfflineBanner offline={offline} working={working} setWorking={setWorking} />
      {away ? <OfflineTill {...props} pack={pack} offline={offline} /> : props.children}
    </>
  )
}
