import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { SelectInput, TextInput } from '../../components/form'
import { Alert, Card, StateBadge } from '../../components/ui'
import { errorMessage } from '../../lib/errors'
import { SaveBar } from '../settings/shared'
import { useCreateUnit, useUnits } from './api'
import { UNIT_DIMENSIONS } from './labels'

const CODE = /^[A-Za-z0-9._-]{1,16}$/

/** FR-CAT-002: platform units (g, kg, ml, l, pcs) plus the business's own (box, tray). */
export function UnitsTab({ canEdit }: { canEdit: boolean }) {
  const { t } = useTranslation()
  const units = useUnits()
  const create = useCreateUnit()
  const [code, setCode] = useState('')
  const [name, setName] = useState('')
  const [dimension, setDimension] = useState<(typeof UNIT_DIMENSIONS)[number]>('count')
  const valid = CODE.test(code.trim()) && name.trim() !== ''

  return (
    <div className="flex flex-col gap-4">
      {units.error && <Alert>{errorMessage(units.error, t)}</Alert>}
      <ul className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
        {units.data?.map((u) => (
          <li
            key={u.id}
            className="flex min-h-12 items-center justify-between gap-2 rounded-xl border border-line bg-card px-3"
          >
            <span>
              <b>{u.code}</b> <span className="text-ink-soft">{u.name}</span>
            </span>
            <StateBadge
              state={u.is_platform ? 'read_only' : 'active'}
              label={t(
                u.is_platform ? 'catalog.units.platform' : `catalog.dimensions.${u.dimension}`,
              )}
            />
          </li>
        ))}
      </ul>
      {canEdit && (
        <Card className="grid gap-3 sm:grid-cols-3 sm:items-end">
          <TextInput
            label={t('catalog.units.code')}
            value={code}
            maxLength={16}
            invalid={code !== '' && !CODE.test(code.trim())}
            onChange={(e) => setCode(e.target.value)}
          />
          <TextInput
            label={t('catalog.units.name')}
            value={name}
            maxLength={80}
            onChange={(e) => setName(e.target.value)}
          />
          <SelectInput
            label={t('catalog.units.dimension')}
            value={dimension}
            onChange={(e) => setDimension(e.target.value as typeof dimension)}
          >
            {UNIT_DIMENSIONS.map((k) => (
              <option key={k} value={k}>
                {t(`catalog.dimensions.${k}`)}
              </option>
            ))}
          </SelectInput>
          <div className="sm:col-span-3">
            <SaveBar
              mutation={create}
              disabled={!valid}
              onSave={() =>
                create.mutate(
                  { code: code.trim(), name: name.trim(), dimension },
                  {
                    onSuccess: () => {
                      setCode('')
                      setName('')
                    },
                  },
                )
              }
            />
          </div>
        </Card>
      )}
    </div>
  )
}
