import { type ReactNode, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useOutletContext } from 'react-router'

import { SelectInput, Tabs } from '../../components/form'
import type { Capabilities } from '../../lib/api/types'
import { useOutlets } from '../../lib/session'
import { QuickPurchaseTab } from './QuickPurchaseTab'
import { ReceiptsTab } from './ReceiptsTab'
import { VendorsTab } from './VendorsTab'

interface Access {
  has: (code: string) => boolean
  currency: string
}

/** Each tab: who sees it (UI only; the server checks every call) and what it shows. */
const TABS: Record<
  string,
  { visible: (a: Access) => boolean; render: (o: string, a: Access) => ReactNode }
> = {
  buy: {
    visible: (a) => a.has('purchasing.receipt.create'),
    render: (o, a) => <QuickPurchaseTab outletId={o} currency={a.currency} />,
  },
  receipts: {
    visible: () => true,
    render: (o, a) => (
      <ReceiptsTab
        outletId={o}
        currency={a.currency}
        canReverse={a.has('purchasing.receipt.reverse')}
      />
    ),
  },
  vendors: {
    visible: () => true,
    render: (_o, a) => <VendorsTab canManage={a.has('purchasing.vendor.manage')} />,
  },
}

/** FR-PUR-001, 004, 011: vendors, quick purchases and goods received per outlet. */
export function PurchasingPage() {
  const { t } = useTranslation()
  const { caps } = useOutletContext<{ caps?: Capabilities }>()
  const a: Access = {
    has: (code) => Boolean(caps?.permissions.includes(code)),
    currency: caps?.currency ?? 'IDR',
  }
  const tabs = Object.keys(TABS).filter((k) => TABS[k].visible(a))
  const outlets = useOutlets()
  const [picked, setPicked] = useState('')
  const outletId = picked || outlets.data?.find((o) => o.is_active)?.id || ''
  const [tab, setTab] = useState(tabs[0] ?? 'receipts')
  return (
    <div className="flex flex-col gap-5">
      <h1 className="font-display text-3xl font-extrabold">{t('purchasing.title')}</h1>
      <SelectInput
        label={t('inventory.outlet')}
        value={outletId}
        onChange={(e) => setPicked(e.target.value)}
        className="max-w-sm"
      >
        {outlets.data?.map((o) => (
          <option key={o.id} value={o.id}>
            {o.name}
          </option>
        ))}
      </SelectInput>
      <Tabs tabs={tabs} value={tab} onChange={setTab} label={(k) => t(`purchasing.tabs.${k}`)} />
      {outletId && <div role="tabpanel">{TABS[tab].render(outletId, a)}</div>}
    </div>
  )
}
