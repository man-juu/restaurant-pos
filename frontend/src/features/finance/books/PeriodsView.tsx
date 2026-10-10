import { useTranslation } from 'react-i18next'

import { Alert, Button, StateBadge } from '../../../components/ui'
import { errorMessage } from '../../../lib/errors'
import { useGlAction, usePeriods } from './glApi'

/** The last 12 months, newest first, with what the ledger knows about them. */
function months(): { year: number; month: number }[] {
  const now = new Date()
  return Array.from({ length: 12 }, (_, i) => {
    const d = new Date(now.getFullYear(), now.getMonth() - i, 1)
    return { year: d.getFullYear(), month: d.getMonth() + 1 }
  })
}

/** FR-FIN-005: close a month when its books are final; reopen to correct (audited). */
export function PeriodsView({ canClose }: { canClose: boolean }) {
  const { t, i18n } = useTranslation()
  const known = usePeriods()
  const act = useGlAction()
  const status = (y: number, m: number) =>
    known.data?.find((p) => p.year === y && p.month === m)?.status ?? 'open'
  return (
    <div className="flex flex-col gap-2">
      {act.error && <Alert>{errorMessage(act.error, t)}</Alert>}
      <ul className="flex flex-col gap-2">
        {months().map(({ year, month }) => {
          const state = status(year, month)
          const label = new Date(year, month - 1, 1).toLocaleDateString(i18n.language, {
            month: 'long',
            year: 'numeric',
          })
          return (
            <li
              key={`${year}-${month}`}
              className="flex items-center justify-between gap-2 rounded-xl border border-line bg-card p-3"
            >
              <span className="font-semibold">{label}</span>
              <span className="flex items-center gap-2">
                <StateBadge state={state} label={t(`books.period.${state}`)} />
                {canClose && (
                  <Button
                    variant="ghost"
                    disabled={act.isPending}
                    onClick={() =>
                      act.mutate({
                        path: `periods/${year}/${month}/${state === 'closed' ? 'reopen' : 'close'}`,
                      })
                    }
                  >
                    {t(state === 'closed' ? 'books.reopen' : 'books.closeMonth')}
                  </Button>
                )}
              </span>
            </li>
          )
        })}
      </ul>
    </div>
  )
}
