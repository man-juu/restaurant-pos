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
import { CatalogSection } from './CatalogSection'
import { DataSection } from './DataSection'
import { DevicesSection } from './DevicesSection'
import { KitchenSection } from './KitchenSection'
import { LimitsSection } from './LimitsSection'
import { FinanceSection, ReportsSection, TablesSection } from './MoreSections'
import { OutletModulesSection } from './OutletModulesSection'
import { PlanningSection } from './PlanningSection'
import { PosSection } from './PosSection'
import { ProductionSection } from './ProductionSection'
import { PurchasingSection } from './PurchasingSection'
import { ReceiptSection } from './ReceiptSection'
import { StockSection } from './StockSection'
import { TaxSection } from './TaxSection'
import { TransfersSection } from './TransfersSection'

type Props = { data: AllSettings; canEdit: boolean; canModules: boolean }

/** One entry per tab: a lookup table instead of a chain of conditions. */
const SECTIONS = {
  modules: (p: Props) => <OutletModulesSection canEdit={p.canModules} />,
  tax: (p: Props) => <TaxSection {...p} />,
  service: (p: Props) => <ServiceSection {...p} />,
  payments: (p: Props) => <PaymentsSection {...p} />,
  pos: (p: Props) => <PosSection {...p} />,
  kitchen: (p: Props) => <KitchenSection {...p} />,
  tables: (p: Props) => <TablesSection {...p} />,
  finance: (p: Props) => <FinanceSection {...p} />,
  receipt: (p: Props) => <ReceiptSection {...p} />,
  devices: () => <DevicesSection />,
  data: () => <DataSection />,
  numbering: (p: Props) => <NumberingSection data={p.data} />,
  approvals: (p: Props) => <ApprovalsSection canEdit={p.canEdit} />,
  limits: (p: Props) => <LimitsSection canEdit={p.canEdit} />,
  stock: (p: Props) => <StockSection {...p} />,
  purchasing: (p: Props) => <PurchasingSection {...p} />,
  production: (p: Props) => <ProductionSection {...p} />,
  planning: (p: Props) => <PlanningSection {...p} />,
  transfers: (p: Props) => <TransfersSection {...p} />,
  reports: (p: Props) => <ReportsSection {...p} />,
  catalog: (p: Props) => <CatalogSection {...p} />,
} satisfies Record<string, (p: Props) => ReactNode>
type Tab = keyof typeof SECTIONS
const TABS = Object.keys(SECTIONS) as Tab[]

export function SettingsPage() {
  const { t } = useTranslation()
  const { caps } = useOutletContext<{ caps?: Capabilities }>()
  const canEdit = Boolean(caps?.permissions.includes('tenant.settings.configure'))
  const canModules = Boolean(caps?.permissions.includes('tenant.module.configure'))
  const settings = useSettings()
  const [tab, setTab] = useState<Tab>('tax')

  return (
    <div className="flex flex-col gap-5">
      <h1 className="font-display text-3xl font-extrabold">{t('settings.title')}</h1>
      {!canEdit && <p className="text-sm text-ink-soft">{t('settings.readOnly')}</p>}
      <Tabs tabs={TABS} value={tab} onChange={setTab} label={(k) => t(`settings.tabs.${k}`)} />
      {settings.error && <Alert>{errorMessage(settings.error, t)}</Alert>}
      {settings.data && (
        <div role="tabpanel">{SECTIONS[tab]({ data: settings.data, canEdit, canModules })}</div>
      )}
    </div>
  )
}
