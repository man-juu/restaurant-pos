import { type ReactNode, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useOutletContext } from 'react-router'

import { SelectInput, Tabs } from '../../components/form'
import type { Capabilities } from '../../lib/api/types'
import { useOutlets } from '../../lib/session'
import { AdjustmentsTab } from './AdjustmentsTab'
import { CountsTab } from './CountsTab'
import { LevelsTab } from './LevelsTab'
import { OpeningTab } from './OpeningTab'
import { StockTab } from './StockTab'
import { ValuationTab } from './ValuationTab'
import { WasteTab } from './WasteTab'

interface Access {
  has: (code: string) => boolean
  showCost: boolean
  currency: string
}

/** Each tab: who sees it (UI only; the server checks every call) and what it shows. */
const TABS: Record<
  string,
  { visible: (a: Access) => boolean; render: (o: string, a: Access) => ReactNode }
> = {
  stock: {
    visible: () => true,
    render: (o, a) => (
      <StockTab
        outletId={o}
        showCost={a.showCost}
        currency={a.currency}
        canAdjust={a.has('inventory.adjustment.create')}
      />
    ),
  },
  waste: {
    visible: (a) => a.has('inventory.waste.create'),
    render: (o, a) => <WasteTab outletId={o} canReverse={a.has('inventory.adjustment.approve')} />,
  },
  adjustments: {
    visible: (a) => a.has('inventory.adjustment.create') || a.has('inventory.adjustment.approve'),
    render: (o, a) => (
      <AdjustmentsTab
        outletId={o}
        canCreate={a.has('inventory.adjustment.create')}
        canApprove={a.has('inventory.adjustment.approve')}
      />
    ),
  },
  counts: {
    visible: (a) => a.has('inventory.count.create') || a.has('inventory.count.approve'),
    render: (o, a) => <CountsTab outletId={o} canApprove={a.has('inventory.count.approve')} />,
  },
  opening: {
    visible: (a) => a.has('inventory.opening.post'),
    render: (o, a) => <OpeningTab key={o} outletId={o} currency={a.currency} />,
  },
  levels: {
    visible: () => true,
    render: (o, a) => (
      <LevelsTab key={o} outletId={o} canManage={a.has('inventory.level.manage')} />
    ),
  },
  valuation: {
    visible: (a) => a.showCost,
    render: (o, a) => <ValuationTab outletId={o} currency={a.currency} />,
  },
}

function access(caps?: Capabilities): Access {
  const has = (code: string) => Boolean(caps?.permissions.includes(code))
  return { has, showCost: has('catalog.cost.view'), currency: caps?.currency ?? 'IDR' }
}

/** FR-INV-001 to 009, 014: stock per outlet and the documents that change it. */
export function InventoryPage() {
  const { t } = useTranslation()
  const { caps } = useOutletContext<{ caps?: Capabilities }>()
  const a = access(caps)
  const tabs = Object.keys(TABS).filter((k) => TABS[k].visible(a))
  const outlets = useOutlets()
  const [picked, setPicked] = useState('')
  const outletId = picked || outlets.data?.find((o) => o.is_active)?.id || ''
  const [tab, setTab] = useState('stock')

  return (
    <div className="flex flex-col gap-5">
      <h1 className="font-display text-3xl font-extrabold">{t('inventory.title')}</h1>
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
      <Tabs tabs={tabs} value={tab} onChange={setTab} label={(k) => t(`inventory.tabs.${k}`)} />
      {outletId && <div role="tabpanel">{TABS[tab].render(outletId, a)}</div>}
    </div>
  )
}
