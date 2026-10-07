import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Alert, Button, Card } from '../../components/ui'
import { errorMessage } from '../../lib/errors'
import { useApprovalRuleMutations, useApprovalRules, useRoles } from './api'
import { inputClass } from './shared'

const DOCS = [
  'purchase_order',
  'transfer',
  'adjustment',
  'count',
  'void',
  'refund',
  'discount',
  'journal',
] as const

export function ApprovalsSection({ canEdit }: { canEdit: boolean }) {
  const { t, i18n } = useTranslation()
  const rules = useApprovalRules()
  const roles = useRoles()
  const { create, remove } = useApprovalRuleMutations()
  const [doc, setDoc] = useState<(typeof DOCS)[number]>('purchase_order')
  const [amount, setAmount] = useState('')
  const [role, setRole] = useState('')
  const roleName = (id: string) => roles.data?.find((r) => r.id === id)?.name ?? '—'
  const amountValue = /^\d{1,13}$/.test(amount) ? Number(amount) : null

  return (
    <Card className="flex flex-col gap-4">
      <p className="text-sm text-ink-soft">{t('settings.approvals.help')}</p>
      {rules.data?.length === 0 && <p className="text-ink-soft">{t('settings.approvals.empty')}</p>}
      <ul className="flex flex-col gap-2">
        {rules.data?.map((r) => (
          <li
            key={r.id}
            className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-line px-3 py-2"
          >
            <span>
              <b>{t(`settings.approvals.docs.${r.document_type}`)}</b>{' '}
              <span className="text-ink-soft">
                {`≥ ${new Intl.NumberFormat(i18n.language === 'id' ? 'id-ID' : 'en-GB').format(r.min_amount)} → ${roleName(r.approver_role_id)}`}
              </span>
            </span>
            {canEdit && (
              <Button variant="ghost" onClick={() => remove.mutate(r.id)}>
                {t('settings.remove')}
              </Button>
            )}
          </li>
        ))}
      </ul>
      {canEdit && (
        <form
          className="grid gap-3 sm:grid-cols-4"
          onSubmit={(e) => {
            e.preventDefault()
            if (amountValue === null || !role) return
            create.mutate({
              document_type: doc,
              min_amount: amountValue,
              approver_role_id: role,
              outlet_id: null,
            })
          }}
        >
          <label className="flex flex-col gap-1 text-sm font-semibold text-ink-soft">
            {t('settings.approvals.document')}
            <select
              className={inputClass}
              value={doc}
              onChange={(e) => setDoc(e.target.value as (typeof DOCS)[number])}
            >
              {DOCS.map((d) => (
                <option key={d} value={d}>
                  {t(`settings.approvals.docs.${d}`)}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1 text-sm font-semibold text-ink-soft">
            {t('settings.approvals.minAmount')}
            <input
              className={inputClass}
              inputMode="numeric"
              value={amount}
              onChange={(e) => setAmount(e.target.value.replace(/\D/g, ''))}
            />
          </label>
          <label className="flex flex-col gap-1 text-sm font-semibold text-ink-soft">
            {t('settings.approvals.role')}
            <select className={inputClass} value={role} onChange={(e) => setRole(e.target.value)}>
              <option value="" />
              {roles.data?.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.name}
                </option>
              ))}
            </select>
          </label>
          <Button
            type="submit"
            className="self-end"
            disabled={amountValue === null || !role || create.isPending}
          >
            {t('settings.add')}
          </Button>
          {create.error ? <Alert>{errorMessage(create.error, t)}</Alert> : null}
        </form>
      )}
    </Card>
  )
}
