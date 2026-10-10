import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { TextInput } from '../../components/form'
import { Alert, Button, Card } from '../../components/ui'
import type { VendorIn, VendorOut } from '../../lib/api/types'
import { errorMessage } from '../../lib/errors'
import { useSaveVendor, useVendors } from './api'

const EMPTY: VendorIn = { name: '', payment_terms_days: 0, lead_time_days: 1, is_active: true }

/** Only the editable fields: the API refuses unknown ones (and never sends bank details back). */
const toInput = (v: VendorOut): VendorIn => ({
  name: v.name,
  contact_name: v.contact_name,
  phone: v.phone,
  email: v.email,
  address: v.address,
  tax_id: v.tax_id,
  payment_terms_days: v.payment_terms_days,
  lead_time_days: v.lead_time_days,
  is_active: v.is_active,
  bank_details: null,
})

/** FR-PUR-001: vendors. Bank details are stored encrypted and never shown in lists. */
export function VendorsTab({ canManage }: { canManage: boolean }) {
  const { t } = useTranslation()
  const vendors = useVendors()
  const [editing, setEditing] = useState<VendorOut | 'new'>()
  if (editing)
    return (
      <VendorForm
        vendor={editing === 'new' ? undefined : editing}
        onDone={() => setEditing(undefined)}
      />
    )
  return (
    <div className="flex flex-col gap-3">
      {canManage && (
        <Button className="self-start" onClick={() => setEditing('new')}>
          {t('purchasing.vendors.new')}
        </Button>
      )}
      {vendors.error && <Alert>{errorMessage(vendors.error, t)}</Alert>}
      {vendors.isSuccess && vendors.data.length === 0 && (
        <p className="text-ink-soft">{t('purchasing.vendors.empty')}</p>
      )}
      <ul className="grid gap-2 lg:grid-cols-2">
        {vendors.data?.map((v) => (
          <li key={v.id}>
            <button
              type="button"
              disabled={!canManage}
              onClick={() => setEditing(v)}
              className="w-full rounded-xl border border-line bg-card p-3 text-left"
            >
              <span className="block font-bold">{v.name}</span>
              <span className="block text-sm text-muted">
                {[v.contact_name, v.phone].filter(Boolean).join(' · ') ||
                  t('purchasing.vendors.noContact')}
              </span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  )
}

function VendorForm({ vendor, onDone }: { vendor?: VendorOut; onDone: () => void }) {
  const { t } = useTranslation()
  const save = useSaveVendor()
  const [d, setD] = useState<VendorIn>(vendor ? toInput(vendor) : EMPTY)
  const set = (patch: Partial<VendorIn>) => setD({ ...d, ...patch })
  const field = (key: 'name' | 'contact_name' | 'phone' | 'email' | 'tax_id') => (
    <TextInput
      label={t(`purchasing.vendors.${key}`)}
      value={d[key] ?? ''}
      maxLength={200}
      onChange={(e) => set({ [key]: e.target.value })}
    />
  )
  return (
    <Card className="flex flex-col gap-3">
      <div className="grid gap-3 sm:grid-cols-2">
        {field('name')}
        {field('contact_name')}
        {field('phone')}
        {field('email')}
        {field('tax_id')}
        <TextInput
          label={t('purchasing.vendors.terms')}
          inputMode="numeric"
          value={String(d.payment_terms_days ?? 0)}
          onChange={(e) => set({ payment_terms_days: Number(e.target.value) || 0 })}
        />
        <TextInput
          label={t('purchasing.vendors.bank')}
          placeholder={vendor?.has_bank_details ? t('purchasing.vendors.bankKept') : ''}
          value={d.bank_details ?? ''}
          maxLength={500}
          onChange={(e) => set({ bank_details: e.target.value || null })}
        />
      </div>
      {save.error ? <Alert>{errorMessage(save.error, t)}</Alert> : null}
      <div className="flex gap-2">
        <Button
          disabled={!d.name.trim() || save.isPending}
          onClick={() => save.mutate({ id: vendor?.id, body: d }, { onSuccess: onDone })}
        >
          {t('settings.save')}
        </Button>
        <Button variant="ghost" onClick={onDone}>
          {t('catalog.cancel')}
        </Button>
      </div>
    </Card>
  )
}
