import { type ReactNode, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useOutletContext } from 'react-router'
import { Tabs } from '../../components/form'
import { Alert } from '../../components/ui'
import type { AllSettings, Capabilities } from '../../lib/api/types'
import { errorMessage } from '../../lib/errors'
import { useSettings } from './api'
import { ApprovalsSection } from './ApprovalsSection'
import { NumberingSection, PaymentsSection, ServiceSection } from './ChargesSections'
import { StockSection } from './StockSection'
import { TaxSection } from './TaxSection'

type Props = { data: AllSettings; canEdit: boolean }

/** One entry per tab: a lookup table instead of a chain of conditions. */
const SECTIONS = {
  tax: (p: Props) => <TaxSection {...p} />,
  service: (p: Props) => <ServiceSection {...p} />,
  payments: (p: Props) => <PaymentsSection {...p} />,
  numbering: (p: Props) => <NumberingSection data={p.data} />,
  approvals: (p: Props) => <ApprovalsSection canEdit={p.canEdit} />,
  stock: (p: Props) => <StockSection {...p} />,
} satisfies Record<string, (p: Props) => ReactNode>
type Tab = keyof typeof SECTIONS
const TABS = Object.keys(SECTIONS) as Tab[]

export function SettingsPage() {
  const { t } = useTranslation()
  const { caps } = useOutletContext<{ caps?: Capabilities }>()
  const canEdit = Boolean(caps?.permissions.includes('tenant.settings.configure'))
  const settings = useSettings()
  const [tab, setTab] = useState<Tab>('tax')

  return (
    <div className="flex flex-col gap-5">
      <h1 className="font-display text-3xl font-extrabold">{t('settings.title')}</h1>
      {!canEdit && <p className="text-sm text-ink-soft">{t('settings.readOnly')}</p>}
      <Tabs tabs={TABS} value={tab} onChange={setTab} label={(k) => t(`settings.tabs.${k}`)} />
      {settings.error && <Alert>{errorMessage(settings.error, t)}</Alert>}
      {settings.data && (
        <div role="tabpanel">{SECTIONS[tab]({ data: settings.data, canEdit })}</div>
      )}
    </div>
  )
}
