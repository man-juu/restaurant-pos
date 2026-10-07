import { clsx } from 'clsx'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useOutletContext } from 'react-router'

import { Alert, Button, Card } from '../../components/ui'
import type { AllSettings, Capabilities } from '../../lib/api/types'
import { errorMessage } from '../../lib/errors'
import { bpToPercent, percentToBp } from '../../lib/percent'
import {
  useApprovalRuleMutations,
  useApprovalRules,
  useRoles,
  useSaveSetting,
  useSettings,
} from './api'

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

function SaveBar({
  mutation,
  onSave,
  disabled,
}: {
  mutation: { isPending: boolean; isSuccess: boolean; error: unknown }
  onSave: () => void
  disabled?: boolean
}) {
  const { t } = useTranslation()
  return (
    <div className="flex flex-wrap items-center gap-3">
      <Button
        onClick={onSave}
        disabled={disabled || mutation.isPending}
        aria-busy={mutation.isPending}
      >
        {mutation.isPending ? t('auth.working') : t('settings.save')}
      </Button>
      {mutation.isSuccess && (
        <span role="status" className="text-sm text-good">
          {t('settings.saved')}
        </span>
      )}
      {mutation.error ? <Alert>{errorMessage(mutation.error, t)}</Alert> : null}
    </div>
  )
}

const inputClass = 'min-h-11 rounded-lg border border-line-strong bg-ground px-3 text-ink'

function TaxSection({ data, canEdit }: { data: AllSettings; canEdit: boolean }) {
  const { t, i18n } = useTranslation()
  const save = useSaveSetting('tax')
  const [rules, setRules] = useState(() =>
    (data.tax.rules ?? []).map((r) => ({ ...r, rateText: bpToPercent(r.rate_bp, i18n.language) })),
  )
  const invalid = rules.some((r) => percentToBp(r.rateText) === null || !r.name.trim())
  const update = (i: number, patch: Partial<(typeof rules)[number]>) =>
    setRules((all) => all.map((r, j) => (j === i ? { ...r, ...patch } : r)))

  return (
    <Card className="flex flex-col gap-4">
      <p className="text-sm text-ink-soft">{t('settings.tax.help')}</p>
      {rules.map((rule, i) => (
        <fieldset
          key={rule.id}
          disabled={!canEdit}
          className="grid gap-3 rounded-xl border border-line p-3 sm:grid-cols-2 lg:grid-cols-5"
        >
          <label className="flex flex-col gap-1 text-sm font-semibold text-ink-soft">
            {t('settings.tax.name')}
            <input
              className={inputClass}
              value={rule.name}
              onChange={(e) => update(i, { name: e.target.value })}
            />
          </label>
          <label className="flex flex-col gap-1 text-sm font-semibold text-ink-soft">
            {t('settings.tax.rate')}
            <input
              className={clsx(inputClass, percentToBp(rule.rateText) === null && 'border-danger')}
              inputMode="decimal"
              value={rule.rateText}
              aria-invalid={percentToBp(rule.rateText) === null}
              onChange={(e) => update(i, { rateText: e.target.value })}
            />
          </label>
          {(['price_includes_tax', 'applies_to_service_charge', 'active'] as const).map((flag) => (
            <label key={flag} className="flex min-h-11 items-center gap-2 text-sm">
              <input
                type="checkbox"
                className="h-5 w-5 accent-[var(--accent)]"
                checked={Boolean(rule[flag])}
                onChange={(e) => update(i, { [flag]: e.target.checked })}
              />
              {t(
                flag === 'price_includes_tax'
                  ? 'settings.tax.included'
                  : flag === 'applies_to_service_charge'
                    ? 'settings.tax.onService'
                    : 'settings.tax.active',
              )}
            </label>
          ))}
        </fieldset>
      ))}
      {invalid && <p className="text-sm text-danger">{t('settings.tax.invalidRate')}</p>}
      {canEdit && (
        <SaveBar
          mutation={save}
          disabled={invalid}
          onSave={() =>
            save.mutate({
              rules: rules.map(({ rateText, ...r }) => ({
                ...r,
                rate_bp: percentToBp(rateText) ?? 0,
              })),
            })
          }
        />
      )}
    </Card>
  )
}

function ServiceSection({ data, canEdit }: { data: AllSettings; canEdit: boolean }) {
  const { t, i18n } = useTranslation()
  const save = useSaveSetting('service_charge')
  const [enabled, setEnabled] = useState(data.service_charge.enabled ?? false)
  const [rate, setRate] = useState(bpToPercent(data.service_charge.rate_bp ?? 0, i18n.language))
  const bp = percentToBp(rate)
  return (
    <Card className="flex flex-col gap-4">
      <fieldset disabled={!canEdit} className="flex flex-wrap items-end gap-4">
        <label className="flex min-h-11 items-center gap-2">
          <input
            type="checkbox"
            className="h-5 w-5 accent-[var(--accent)]"
            checked={enabled}
            onChange={(e) => setEnabled(e.target.checked)}
          />
          {t('settings.service.enabled')}
        </label>
        <label className="flex flex-col gap-1 text-sm font-semibold text-ink-soft">
          {t('settings.service.rate')}
          <input
            className={inputClass}
            inputMode="decimal"
            value={rate}
            aria-invalid={bp === null}
            onChange={(e) => setRate(e.target.value)}
          />
        </label>
      </fieldset>
      {canEdit && (
        <SaveBar
          mutation={save}
          disabled={bp === null}
          onSave={() => save.mutate({ ...data.service_charge, enabled, rate_bp: bp ?? 0 })}
        />
      )}
    </Card>
  )
}

function PaymentsSection({ data, canEdit }: { data: AllSettings; canEdit: boolean }) {
  const { t } = useTranslation()
  const save = useSaveSetting('payment_methods')
  const [methods, setMethods] = useState(data.payment_methods.methods ?? [])
  return (
    <Card className="flex flex-col gap-3">
      {methods.map((m, i) => (
        <label
          key={m.code}
          className="flex min-h-11 items-center justify-between gap-3 rounded-xl border border-line px-3"
        >
          <span>
            <span className="font-bold">{m.name}</span>{' '}
            <span className="text-sm text-muted">{t(`settings.payments.kinds.${m.kind}`)}</span>
          </span>
          <input
            type="checkbox"
            className="h-5 w-5 accent-[var(--accent)]"
            disabled={!canEdit}
            checked={m.active ?? true}
            aria-label={t('settings.payments.active')}
            onChange={(e) =>
              setMethods((all) =>
                all.map((x, j) => (j === i ? { ...x, active: e.target.checked } : x)),
              )
            }
          />
        </label>
      ))}
      {canEdit && <SaveBar mutation={save} onSave={() => save.mutate({ methods })} />}
    </Card>
  )
}

function NumberingSection({ data }: { data: AllSettings }) {
  const { t } = useTranslation()
  const year = new Date().getFullYear()
  return (
    <Card className="overflow-x-auto p-0">
      <table className="w-full min-w-[480px] text-sm">
        <thead>
          <tr className="text-left text-xs tracking-wider text-muted uppercase">
            <th className="px-4 py-3">{t('settings.numbering.document')}</th>
            <th className="px-4 py-3">{t('settings.numbering.prefix')}</th>
            <th className="px-4 py-3">{t('settings.numbering.example')}</th>
          </tr>
        </thead>
        <tbody>
          {Object.entries(data.numbering.formats ?? {}).map(([doc, f]) => (
            <tr key={doc} className="border-t border-line">
              <td className="px-4 py-3">
                {t(`settings.numbering.docs.${doc}`, { defaultValue: doc })}
              </td>
              <td className="px-4 py-3 font-mono">{f.prefix}</td>
              <td className="px-4 py-3 font-mono text-ink-soft">
                {`${f.prefix}${f.reset === 'never' ? '' : `-${year}`}-${'1'.padStart(f.padding ?? 5, '0')}`}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  )
}

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

function ApprovalsSection({ canEdit }: { canEdit: boolean }) {
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
