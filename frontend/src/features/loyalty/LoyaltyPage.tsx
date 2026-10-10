import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useOutletContext } from 'react-router'

import { Tabs } from '../../components/form'
import type { Capabilities, CustomerOut } from '../../lib/api/types'
import { formatMoney, intlLocale } from '../../lib/format'
import { GuestCard } from './GuestCard'
import { GuestPicker } from './GuestPicker'
import { VouchersPanel } from './VouchersPanel'

type Tab = 'guests' | 'vouchers'

/** FR-SAL-016: guests' points and vouchers. Points are earned on the paid receipt (till). */
export function LoyaltyPage() {
  const { t, i18n } = useTranslation()
  const { caps } = useOutletContext<{ caps?: Capabilities }>()
  const can = (code: string) => Boolean(caps?.permissions.includes(code))
  const currency = caps?.currency ?? 'IDR'
  const money = (v: number) => formatMoney(v, currency, intlLocale(i18n.language))
  const tabs: Tab[] = can('loyalty.voucher.manage') ? ['guests', 'vouchers'] : ['guests']
  const [tab, setTab] = useState<Tab>('guests')
  const [guest, setGuest] = useState<CustomerOut | null>(null)
  return (
    <div className="flex flex-col gap-4">
      <h1 className="font-display text-3xl font-extrabold">{t('loyalty.title')}</h1>
      <Tabs tabs={tabs} value={tab} onChange={setTab} label={(k) => t(`loyalty.tabs.${k}`)} />
      <div role="tabpanel" className="flex flex-col gap-3">
        {tab === 'guests' && <GuestPicker onPick={setGuest} />}
        {tab === 'guests' && guest && (
          <GuestCard guest={guest} money={money} canRedeem={can('loyalty.points.redeem')} />
        )}
        {tab === 'vouchers' && <VouchersPanel money={money} currency={currency} />}
      </div>
    </div>
  )
}
