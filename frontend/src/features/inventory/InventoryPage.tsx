import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useOutletContext } from 'react-router'

import { SelectInput, Tabs } from '../../components/form'
import type { Capabilities } from '../../lib/api/types'
import { useOutlets } from '../../lib/session'
import { OpeningTab } from './OpeningTab'
import { StockTab } from './StockTab'
import { ValuationTab } from './ValuationTab'

type Tab = 'stock' | 'opening' | 'valuation'

function access(caps?: Capabilities) {
  const has = (code: string) => Boolean(caps?.permissions.includes(code))
  const tabs: Tab[] = ['stock']
  if (has('inventory.opening.post')) tabs.push('opening')
  if (has('catalog.cost.view')) tabs.push('valuation')
  return { tabs, showCost: has('catalog.cost.view'), currency: caps?.currency ?? 'IDR' }
}

/** FR-INV-001, 003, 005, 014: stock per outlet, opening stock and valuation. */
export function InventoryPage() {
  const { t } = useTranslation()
  const { caps } = useOutletContext<{ caps?: Capabilities }>()
  const { tabs, showCost, currency } = access(caps)
  const outlets = useOutlets()
  const [picked, setPicked] = useState('')
  const outletId = picked || outlets.data?.find((o) => o.is_active)?.id || ''
  const [tab, setTab] = useState<Tab>('stock')

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
      {outletId && (
        <div role="tabpanel">
          {tab === 'stock' && (
            <StockTab outletId={outletId} showCost={showCost} currency={currency} />
          )}
          {tab === 'opening' && (
            <OpeningTab key={outletId} outletId={outletId} currency={currency} />
          )}
          {tab === 'valuation' && <ValuationTab outletId={outletId} currency={currency} />}
        </div>
      )}
    </div>
  )
}
