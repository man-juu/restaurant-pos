import { type ReactNode, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useOutletContext } from 'react-router'

import { SelectInput, Tabs } from '../../components/form'
import type { Capabilities } from '../../lib/api/types'
import { useOutlets } from '../../lib/session'
import { BillsTab } from './BillsTab'
import { OrdersTab } from './OrdersTab'
import { QuickPurchaseTab } from './QuickPurchaseTab'
import { ReceiptsTab } from './ReceiptsTab'
import { ReorderTab } from './ReorderTab'
import { ReturnsTab } from './ReturnsTab'
import { VendorsTab } from './VendorsTab'

interface Access {
  has: (code: string) => boolean
  currency: string
  goTo: (tab: string) => void
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
  orders: {
    visible: (a) => a.has('purchasing.vendor.view'),
    render: (o, a) => (
      <OrdersTab
        outletId={o}
        currency={a.currency}
        can={{
          create: a.has('purchasing.order.create'),
          approve: a.has('purchasing.order.approve'),
          receive: a.has('purchasing.receipt.create'),
        }}
      />
    ),
  },
  reorder: {
    visible: (a) => a.has('purchasing.order.create'),
    render: (o, a) => <ReorderTab outletId={o} onDrafted={() => a.goTo('orders')} />,
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
  returns: {
    visible: () => true,
    render: (o, a) => (
      <ReturnsTab
        outletId={o}
        currency={a.currency}
        can={{
          create: a.has('purchasing.return.create'),
          reverse: a.has('purchasing.receipt.reverse'),
          credit: a.has('purchasing.bill.manage'),
        }}
      />
    ),
  },
  bills: {
    visible: (a) => a.has('purchasing.bill.view'),
    render: (o, a) => (
      <BillsTab
        outletId={o}
        currency={a.currency}
        can={{ manage: a.has('purchasing.bill.manage'), pay: a.has('purchasing.bill.pay') }}
      />
    ),
  },
  vendors: {
    visible: () => true,
    render: (_o, a) => <VendorsTab canManage={a.has('purchasing.vendor.manage')} />,
  },
}

function access(caps: Capabilities | undefined, goTo: (tab: string) => void): Access {
  return {
    has: (code) => Boolean(caps?.permissions.includes(code)),
    currency: caps?.currency ?? 'IDR',
    goTo,
  }
}

const pick = (tabs: string[], tab: string) => (tabs.includes(tab) ? tab : (tabs[0] ?? 'receipts'))

/** FR-PUR-001, 004, 011: vendors, quick purchases and goods received per outlet. */
export function PurchasingPage() {
  const { t } = useTranslation()
  const { caps } = useOutletContext<{ caps?: Capabilities }>()
  const [tab, setTab] = useState('')
  const a = access(caps, setTab)
  const tabs = Object.keys(TABS).filter((k) => TABS[k].visible(a))
  const outlets = useOutlets('purchasing')
  const [picked, setPicked] = useState('')
  const outletId = picked || outlets.data?.find((o) => o.is_active)?.id || ''
  const current = pick(tabs, tab)
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
      <Tabs
        tabs={tabs}
        value={current}
        onChange={setTab}
        label={(k) => t(`purchasing.tabs.${k}`)}
      />
      {outletId && <div role="tabpanel">{TABS[current].render(outletId, a)}</div>}
    </div>
  )
}
