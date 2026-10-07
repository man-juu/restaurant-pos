import { clsx } from 'clsx'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useOutletContext } from 'react-router'
import { Alert } from '../../components/ui'
import type { Capabilities } from '../../lib/api/types'
import { errorMessage } from '../../lib/errors'
import { useSettings } from './api'
import { ApprovalsSection } from './ApprovalsSection'
import { NumberingSection, PaymentsSection, ServiceSection } from './ChargesSections'
import { TaxSection } from './TaxSection'

const TABS = ['tax', 'service', 'payments', 'numbering', 'approvals'] as const
type Tab = (typeof TABS)[number]

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
      <div role="tablist" className="flex flex-wrap gap-2">
        {TABS.map((key) => (
          <button
            key={key}
            role="tab"
            type="button"
            aria-selected={tab === key}
            onClick={() => setTab(key)}
            className={clsx(
              'min-h-11 rounded-xl border px-4 text-sm font-bold',
              tab === key ? 'border-accent bg-raised text-ink' : 'border-line-strong text-ink-soft',
            )}
          >
            {t(`settings.tabs.${key}`)}
          </button>
        ))}
      </div>
      {settings.error && <Alert>{errorMessage(settings.error, t)}</Alert>}
      {settings.data && (
        <div role="tabpanel">
          {tab === 'tax' && <TaxSection data={settings.data} canEdit={canEdit} />}
          {tab === 'service' && <ServiceSection data={settings.data} canEdit={canEdit} />}
          {tab === 'payments' && <PaymentsSection data={settings.data} canEdit={canEdit} />}
          {tab === 'numbering' && <NumberingSection data={settings.data} />}
          {tab === 'approvals' && <ApprovalsSection canEdit={canEdit} />}
        </div>
      )}
    </div>
  )
}
