import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useOutletContext } from 'react-router'

import { SelectInput, Tabs } from '../../components/form'
import { Alert, Button } from '../../components/ui'
import type { Capabilities, OutletOut } from '../../lib/api/types'
import { errorMessage } from '../../lib/errors'
import { useOutlets } from '../../lib/session'
import { useTransfers } from './api'
import { ChargesTab } from './ChargesTab'
import { RequestForm } from './RequestForm'
import { StandingTab } from './StandingTab'
import { type Can, TransferCard } from './TransferCard'

const TABS = ['list', 'standing', 'charges'] as const
type Tab = (typeof TABS)[number]

const firstActive = (all: OutletOut[]) => all.find((o) => o.is_active)?.id ?? ''

/** The charges report shows costs: only for those who may see them. */
const visibleTabs = (caps?: Capabilities) =>
  TABS.filter((k) => k !== 'charges' || Boolean(caps?.permissions.includes('catalog.cost.view')))

function abilities(caps?: Capabilities): Can {
  const has = (code: string) => Boolean(caps?.permissions.includes(code))
  return {
    request: has('transfers.transfer.request'),
    approve: has('transfers.transfer.approve'),
    receive: has('transfers.transfer.receive'),
  }
}

/** FR-TRF-001 to 006: requests in and out of this outlet, and the next step for each. */
export function TransfersPage() {
  const { t } = useTranslation()
  const { caps } = useOutletContext<{ caps?: Capabilities }>()
  const every = useOutlets().data ?? []
  const all = every.filter((o) => !o.modules_off?.includes('transfers'))
  const [picked, setPicked] = useState('')
  const outletId = picked || firstActive(all)
  const names = Object.fromEntries(every.map((o) => [o.id, o.name]))
  const can = abilities(caps)
  const currency = caps?.currency ?? 'IDR'
  const [tab, setTab] = useState<Tab>('list')
  const tabs = visibleTabs(caps)
  return (
    <div className="flex flex-col gap-5">
      <h1 className="font-display text-3xl font-extrabold">{t('transfers.title')}</h1>
      <SelectInput
        label={t('inventory.outlet')}
        value={outletId}
        onChange={(e) => setPicked(e.target.value)}
        className="max-w-sm"
      >
        {all.map((o) => (
          <option key={o.id} value={o.id}>
            {o.name}
          </option>
        ))}
      </SelectInput>
      <Tabs tabs={tabs} value={tab} onChange={setTab} label={(k) => t(`standing.tabs.${k}`)} />
      {outletId && (
        <TabBody
          tab={tab}
          outletId={outletId}
          outlets={all}
          names={names}
          currency={currency}
          can={can}
        />
      )}
    </div>
  )
}

function TransferList({
  outletId,
  names,
  currency,
  can,
}: {
  outletId: string
  names: Record<string, string>
  currency: string
  can: Can
}) {
  const { t, i18n } = useTranslation()
  const list = useTransfers(outletId, i18n.language)
  return (
    <>
      {list.error && <Alert>{errorMessage(list.error, t)}</Alert>}
      {list.isSuccess && list.data.length === 0 && (
        <p className="text-ink-soft">{t('transfers.empty')}</p>
      )}
      {list.data?.map((tr) => (
        <TransferCard
          key={tr.id}
          transfer={tr}
          outletId={outletId}
          names={names}
          currency={currency}
          can={can}
        />
      ))}
    </>
  )
}

function RequestArea({ outletId, canRequest }: { outletId: string; canRequest: boolean }) {
  const { t } = useTranslation()
  const outlets = useOutlets()
  const [asking, setAsking] = useState(false)
  if (asking)
    return (
      <RequestForm
        outletId={outletId}
        outlets={outlets.data ?? []}
        onDone={() => setAsking(false)}
      />
    )
  if (!canRequest) return null
  return (
    <Button className="self-start" onClick={() => setAsking(true)}>
      {t('transfers.new')}
    </Button>
  )
}

function TabBody(p: {
  tab: Tab
  outletId: string
  outlets: OutletOut[]
  names: Record<string, string>
  currency: string
  can: Can
}) {
  if (p.tab === 'standing')
    return <StandingTab outletId={p.outletId} outlets={p.outlets} canRequest={p.can.request} />
  if (p.tab === 'charges') return <ChargesTab names={p.names} currency={p.currency} />
  return (
    <>
      <RequestArea outletId={p.outletId} canRequest={p.can.request} />
      <TransferList outletId={p.outletId} names={p.names} currency={p.currency} can={p.can} />
    </>
  )
}
