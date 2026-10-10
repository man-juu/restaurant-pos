import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { SelectInput, TextInput } from '../../../components/form'
import { Alert, Button, Card } from '../../../components/ui'
import type { GlAccountOut } from '../../../lib/api/types'
import { errorMessage } from '../../../lib/errors'
import { useGlAction } from './glApi'

const TYPES = ['asset', 'liability', 'equity', 'revenue', 'expense'] as const

/** FR-FIN-002, 003: the chart of accounts. Each role (cash, sales, ...) is held by one account;
 *  automatic journals post there, so moving a role is how posting rules are changed. */
export function ChartView({ accounts, canEdit }: { accounts: GlAccountOut[]; canEdit: boolean }) {
  const { t } = useTranslation()
  const act = useGlAction()
  const roles = accounts.filter((a) => a.system_key)
  return (
    <div className="flex flex-col gap-3">
      {canEdit && <NewAccount />}
      {act.error && <Alert>{errorMessage(act.error, t)}</Alert>}
      <ul className="flex flex-col gap-1">
        {accounts.map((a) => {
          const takeable = roles.filter((r) => r.type === a.type && r.id !== a.id)
          return (
            <li
              key={a.id}
              className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-line bg-card px-3 py-2"
            >
              <span>
                <b>{a.code}</b> {a.name}
                <span className="ml-2 text-sm text-ink-soft">{t(`books.types.${a.type}`)}</span>
                {a.system_key && (
                  <span className="ml-2 text-sm text-accent">
                    {t('books.role', { role: a.system_key })}
                  </span>
                )}
              </span>
              {canEdit && takeable.length > 0 && (
                <SelectInput
                  label={t('books.giveRole')}
                  value=""
                  onChange={(e) =>
                    e.target.value &&
                    act.mutate({
                      method: 'PUT',
                      path: `accounts/${a.id}/role`,
                      body: { system_key: e.target.value },
                    })
                  }
                >
                  <option value="">—</option>
                  {takeable.map((r) => (
                    <option key={r.id} value={r.system_key ?? ''}>
                      {r.system_key}
                    </option>
                  ))}
                </SelectInput>
              )}
            </li>
          )
        })}
      </ul>
    </div>
  )
}

function NewAccount() {
  const { t } = useTranslation()
  const act = useGlAction()
  const [code, setCode] = useState('')
  const [name, setName] = useState('')
  const [type, setType] = useState<(typeof TYPES)[number]>('expense')
  const save = () =>
    act.mutate(
      { path: 'accounts', body: { code: code.trim(), name: name.trim(), type } },
      { onSuccess: () => (setCode(''), setName('')) },
    )
  return (
    <Card className="flex flex-wrap items-end gap-2">
      <TextInput
        label={t('books.code')}
        className="w-28"
        value={code}
        maxLength={20}
        onChange={(e) => setCode(e.target.value)}
      />
      <TextInput
        label={t('books.name')}
        value={name}
        maxLength={120}
        onChange={(e) => setName(e.target.value)}
      />
      <SelectInput
        label={t('books.type')}
        value={type}
        onChange={(e) => setType(e.target.value as (typeof TYPES)[number])}
      >
        {TYPES.map((x) => (
          <option key={x} value={x}>
            {t(`books.types.${x}`)}
          </option>
        ))}
      </SelectInput>
      <Button disabled={!code.trim() || !name.trim() || act.isPending} onClick={save}>
        {t('books.addAccount')}
      </Button>
      {act.error && <Alert>{errorMessage(act.error, t)}</Alert>}
    </Card>
  )
}
