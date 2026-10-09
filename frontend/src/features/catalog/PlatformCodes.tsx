import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { TextInput } from '../../components/form'
import { Alert, Button, Card } from '../../components/ui'
import { request } from '../../lib/api/client'
import type { ItemSummary } from '../../lib/api/types'
import { errorMessage } from '../../lib/errors'
import { useItems } from './api'
import { ComponentPicker } from './ComponentPicker'

interface Row {
  platform_code: string
  item_id: string
  label: string
}

const MENU = ['menu'] as const
const path = (id: string) => `/api/v1/catalog/channels/${id}/mappings`

/** FR-CAT-010: the code the platform uses for each menu item on this channel. */
export function PlatformCodes({ channelId }: { channelId: string }) {
  const { t, i18n } = useTranslation()
  const menu = useItems({ q: '', type: 'menu', lang: i18n.language })
  const names = Object.fromEntries((menu.data?.pages[0]?.items ?? []).map((i) => [i.id, i.name]))
  const client = useQueryClient()
  const saved = useQuery({
    queryKey: ['mappings', channelId],
    queryFn: () => request<{ platform_code: string; item_id: string }[]>('GET', path(channelId)),
  })
  const save = useMutation({
    mutationFn: (rows: Row[]) =>
      request('PUT', path(channelId), {
        mappings: rows.map(({ platform_code, item_id }) => ({ platform_code, item_id })),
      }),
    onSuccess: () => client.invalidateQueries({ queryKey: ['mappings', channelId] }),
  })
  const [edits, setEdits] = useState<Row[]>()
  const rows = edits ?? (saved.data ?? []).map((m) => ({ ...m, label: names[m.item_id] ?? '' }))
  const add = (item: ItemSummary) =>
    setEdits([...rows, { platform_code: '', item_id: item.id, label: item.name }])
  const ok = rows.every((r) => r.platform_code.trim() !== '')
  return (
    <Card className="flex flex-col gap-3">
      <h3 className="font-bold">{t('catalog.platformCodes.title')}</h3>
      <p className="text-sm text-ink-soft">{t('catalog.platformCodes.help')}</p>
      {rows.map((r, i) => (
        <div key={r.item_id} className="flex flex-wrap items-end gap-2">
          <TextInput
            label={t('catalog.platformCodes.code', { name: r.label })}
            value={r.platform_code}
            maxLength={64}
            onChange={(e) =>
              setEdits(rows.map((x, j) => (j === i ? { ...x, platform_code: e.target.value } : x)))
            }
          />
          <Button variant="ghost" onClick={() => setEdits(rows.filter((_, j) => j !== i))}>
            {t('catalog.platformCodes.remove')}
          </Button>
        </div>
      ))}
      <ComponentPicker
        exclude={new Set(rows.map((r) => r.item_id))}
        onPick={add}
        label={t('catalog.platformCodes.add')}
        types={MENU}
      />
      {save.error ? <Alert>{errorMessage(save.error, t)}</Alert> : null}
      <Button
        className="self-start"
        disabled={!edits || !ok || save.isPending}
        onClick={() => save.mutate(rows, { onSuccess: () => setEdits(undefined) })}
      >
        {t('catalog.platformCodes.save')}
      </Button>
    </Card>
  )
}
