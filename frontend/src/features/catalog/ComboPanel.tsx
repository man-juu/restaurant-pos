import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { TextInput } from '../../components/form'
import { Alert, Button, Card } from '../../components/ui'
import { request } from '../../lib/api/client'
import { errorMessage } from '../../lib/errors'
import { SaveBar } from '../settings/shared'
import { ComponentPicker } from './ComponentPicker'

interface Part {
  item_id: string
  qty: string
  name?: string
}

const QTY = /^\d{1,3}([.,]\d{1,4})?$/

/** FR-CAT-011: a combo is this menu item sold at its own price, made of other menu items. */
export function ComboPanel({ itemId, canEdit }: { itemId: string; canEdit: boolean }) {
  const { t } = useTranslation()
  const parts = useQuery({
    queryKey: ['combo', itemId],
    queryFn: () => request<Part[]>('GET', `/api/v1/catalog/items/${itemId}/combo`),
  })
  if (!parts.data) return null
  return (
    <ComboEditor
      key={parts.dataUpdatedAt}
      itemId={itemId}
      initial={parts.data}
      canEdit={canEdit}
      title={t('catalog.combo.title')}
    />
  )
}

function ComboEditor({
  itemId,
  initial,
  canEdit,
  title,
}: {
  itemId: string
  initial: Part[]
  canEdit: boolean
  title: string
}) {
  const { t } = useTranslation()
  const client = useQueryClient()
  const [rows, setRows] = useState<Part[]>(
    initial.map((p) => ({ ...p, qty: String(Number(p.qty)) })),
  )
  const save = useMutation({
    mutationFn: () =>
      request<Part[]>('PUT', `/api/v1/catalog/items/${itemId}/combo`, {
        parts: rows.map((r) => ({ item_id: r.item_id, qty: r.qty.replace(',', '.') })),
      }),
    onSuccess: () => client.invalidateQueries({ queryKey: ['combo', itemId] }),
  })
  const valid = rows.every((r) => QTY.test(r.qty) && Number(r.qty.replace(',', '.')) > 0)
  return (
    <Card className="flex flex-col gap-3">
      <h2 className="font-display text-xl font-bold">{title}</h2>
      <p className="text-sm text-ink-soft">{t('catalog.combo.help')}</p>
      <ul className="flex flex-col gap-2">
        {rows.map((r, i) => (
          <li key={r.item_id} className="flex flex-wrap items-end gap-2">
            <span className="min-w-32 font-semibold">
              {r.name ?? t('catalog.combo.part', { n: i + 1 })}
            </span>
            <TextInput
              label={t('catalog.recipe.qty')}
              inputMode="decimal"
              value={r.qty}
              disabled={!canEdit}
              onChange={(e) =>
                setRows(rows.map((x, j) => (j === i ? { ...x, qty: e.target.value } : x)))
              }
            />
            {canEdit && (
              <Button variant="ghost" onClick={() => setRows(rows.filter((_, j) => j !== i))}>
                {t('catalog.combo.remove')}
              </Button>
            )}
          </li>
        ))}
      </ul>
      {canEdit && (
        <>
          <ComponentPicker
            types={['menu']}
            label={t('catalog.combo.add')}
            exclude={new Set([itemId, ...rows.map((r) => r.item_id)])}
            onPick={(item) => setRows([...rows, { item_id: item.id, qty: '1', name: item.name }])}
          />
          {save.error ? <Alert>{errorMessage(save.error, t)}</Alert> : null}
          <SaveBar mutation={save} disabled={!valid} onSave={() => save.mutate()} />
        </>
      )}
    </Card>
  )
}
