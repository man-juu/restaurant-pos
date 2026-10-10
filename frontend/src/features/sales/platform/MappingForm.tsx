import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { SelectInput, TextInput } from '../../../components/form'
import { Alert, Button } from '../../../components/ui'
import type { ColumnMapIn, ColumnMapOut } from '../../../lib/api/types'
import { errorMessage } from '../../../lib/errors'
import { fileColumns, useSaveColumnMap } from './api'

const FIELDS = ['date_column', 'code_column', 'qty_column', 'amount_column'] as const
const FORMATS = ['dmy', 'mdy', 'ymd'] as const
const EMPTY: ColumnMapIn = {
  date_column: '',
  code_column: '',
  qty_column: '',
  amount_column: '',
  date_format: 'dmy',
}

/** FR-IMP-004: which column holds what, saved per platform so the next file needs no setup.
 * Column names can be typed or picked from a sample file's header. */
export function MappingForm({
  channelId,
  saved,
  onSaved,
}: {
  channelId: string
  saved: ColumnMapOut | null
  onSaved: () => void
}) {
  const { t } = useTranslation()
  const [draft, setDraft] = useState<ColumnMapIn>(saved ?? EMPTY)
  const [columns, setColumns] = useState<string[]>([])
  const save = useSaveColumnMap(channelId)
  const ready = draft.date_column && draft.code_column && draft.qty_column
  const submit = () =>
    save.mutate({ ...draft, amount_column: draft.amount_column || null }, { onSuccess: onSaved })
  return (
    <div className="flex flex-col gap-3">
      <p className="text-sm text-ink-soft">{t('sales.platform.mapHelp')}</p>
      <label className="flex flex-col gap-1 text-sm font-semibold text-ink-soft">
        {t('sales.platform.sample')}
        <input
          type="file"
          accept=".csv,.xlsx"
          onChange={(e) => {
            const file = e.target.files?.[0]
            if (file) void fileColumns(file).then(setColumns, () => setColumns([]))
          }}
        />
      </label>
      <datalist id="platform-columns">
        {columns.map((c) => (
          <option key={c} value={c} />
        ))}
      </datalist>
      <div className="grid gap-3 sm:grid-cols-2">
        {FIELDS.map((f) => (
          <TextInput
            key={f}
            label={t(`sales.platform.fields.${f}`)}
            list="platform-columns"
            maxLength={100}
            value={draft[f] ?? ''}
            onChange={(e) => setDraft({ ...draft, [f]: e.target.value })}
          />
        ))}
        <SelectInput
          label={t('sales.platform.dateFormat')}
          value={draft.date_format}
          onChange={(e) =>
            setDraft({ ...draft, date_format: e.target.value as ColumnMapIn['date_format'] })
          }
        >
          {FORMATS.map((f) => (
            <option key={f} value={f}>
              {t(`sales.platform.formats.${f}`)}
            </option>
          ))}
        </SelectInput>
      </div>
      {save.error && <Alert>{errorMessage(save.error, t)}</Alert>}
      <Button disabled={!ready || save.isPending} onClick={submit}>
        {t('sales.platform.saveMap')}
      </Button>
    </div>
  )
}
