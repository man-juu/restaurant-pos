import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useOutletContext } from 'react-router'

import { SelectInput } from '../../components/form'
import { Button } from '../../components/ui'
import type { Capabilities } from '../../lib/api/types'
import { useSession } from '../../lib/session'
import { RefundApprovals } from './RefundApprovals'
import { ShiftOpen, ShiftSummary } from './ShiftPanel'
import { Till } from './Till'
import { type TillContext, useTillContext } from './useTillContext'

/** FR-SAL-004 to 006, 009: the cashier screen. */
export function PosPage() {
  const { t } = useTranslation()
  const { caps } = useOutletContext<{ caps?: Capabilities }>()
  const till = useTillContext(caps)
  const userId = useSession().data?.user.id
  const [showShift, setShowShift] = useState(false)
  const ready = !till.needsShift && till.outletId !== '' && till.channelId !== ''
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end gap-3">
        <h1 className="mr-auto font-display text-3xl font-extrabold">{t('pos.title')}</h1>
        <Pickers till={till} />
        {till.shift && (
          <Button
            variant="ghost"
            aria-expanded={showShift}
            onClick={() => setShowShift(!showShift)}
          >
            {t('pos.shift.button')}
          </Button>
        )}
      </div>
      <TopPanels till={till} showShift={showShift} userId={userId} />
      {ready && (
        <Till
          key={`${till.outletId}-${till.channelId}`}
          outletId={till.outletId}
          channelId={till.channelId}
          currency={till.currency}
          can={till.can}
          methods={till.methods}
          pos={till.pos}
        />
      )}
    </div>
  )
}

function Pickers({ till }: { till: TillContext }) {
  const { t } = useTranslation()
  return (
    <>
      <SelectInput
        label={t('pos.outlet')}
        value={till.outletId}
        onChange={(e) => till.setOutlet(e.target.value)}
      >
        {till.outlets.map((o) => (
          <option key={o.id} value={o.id}>
            {o.name}
          </option>
        ))}
      </SelectInput>
      <SelectInput
        label={t('pos.channel')}
        value={till.channelId}
        onChange={(e) => till.setChannel(e.target.value)}
      >
        {till.channels.map((c) => (
          <option key={c.id} value={c.id}>
            {c.name}
          </option>
        ))}
      </SelectInput>
    </>
  )
}

/** Above the till: the drawer when asked for, refunds to approve, opening a shift. */
function TopPanels({
  till,
  showShift,
  userId,
}: {
  till: TillContext
  showShift: boolean
  userId?: string
}) {
  return (
    <>
      {till.shift && showShift && <ShiftSummary shift={till.shift} currency={till.currency} />}
      {till.can.refund && till.outletId !== '' && (
        <RefundApprovals outletId={till.outletId} currency={till.currency} userId={userId} />
      )}
      {till.needsShift && <ShiftOpen outletId={till.outletId} currency={till.currency} />}
    </>
  )
}
