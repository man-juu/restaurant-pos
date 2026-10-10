import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Tabs } from '../../../components/form'
import { Alert } from '../../../components/ui'
import type { GlAccountOut } from '../../../lib/api/types'
import { errorMessage } from '../../../lib/errors'
import { ChartView } from './ChartView'
import { JournalsView } from './JournalsView'
import { PeriodsView } from './PeriodsView'
import { ReconcileView } from './ReconcileView'
import { SetupForm } from './SetupForm'
import { StatementsView } from './StatementsView'
import { useGlAccounts, useSetup } from './glApi'

const VIEWS = ['journals', 'statements', 'reconcile', 'chart', 'periods'] as const
type View = (typeof VIEWS)[number]
type Can = { setup: boolean; post: boolean; close: boolean }

/** FR-FIN-002 to 005, 009: the general ledger: start the books, journals, statements, close. */
export function BooksTab({
  from,
  to,
  currency,
  can,
}: {
  from: string
  to: string
  currency: string
  can: Can
}) {
  const { t } = useTranslation()
  const setup = useSetup()
  const accounts = useGlAccounts(Boolean(setup.data))
  const [view, setView] = useState<View>('journals')
  if (setup.error) return <Alert>{errorMessage(setup.error, t)}</Alert>
  if (setup.isSuccess && !setup.data) return <SetupForm canSetup={can.setup} />
  if (!setup.data) return null
  return (
    <div className="flex flex-col gap-3">
      <p className="text-sm text-ink-soft">{t('books.since', { date: setup.data.start_date })}</p>
      <Tabs tabs={VIEWS} value={view} onChange={setView} label={(k) => t(`books.views.${k}`)} />
      <ViewPanel
        view={view}
        from={from}
        to={to}
        currency={currency}
        can={can}
        accounts={accounts.data ?? []}
      />
    </div>
  )
}

type PanelProps = {
  view: View
  from: string
  to: string
  currency: string
  can: Can
  accounts: GlAccountOut[]
}

function ViewPanel({ view, from, to, currency, can, accounts }: PanelProps) {
  if (view === 'journals')
    return (
      <JournalsView
        from={from}
        to={to}
        currency={currency}
        accounts={accounts}
        canPost={can.post}
      />
    )
  if (view === 'statements') return <StatementsView from={from} to={to} currency={currency} />
  if (view === 'reconcile') return <ReconcileView currency={currency} />
  if (view === 'chart') return <ChartView accounts={accounts} canEdit={can.setup} />
  return <PeriodsView canClose={can.close} />
}
