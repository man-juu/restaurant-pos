import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'

import { Alert, Button, Card } from '../../components/ui'
import { request } from '../../lib/api/client'
import type { SuggestionGroup } from '../../lib/api/types'
import { errorMessage } from '../../lib/errors'
import { todayIso } from '../catalog/labels'
import { useSaveOrder } from './orderApi'

const useSuggestions = (outletId: string, lang: string) =>
  useQuery({
    queryKey: ['reorder', outletId, lang],
    queryFn: () =>
      request<SuggestionGroup[]>(
        'GET',
        `/api/v1/purchasing/reorder-suggestions?outlet_id=${outletId}&lang=${lang.slice(0, 2)}`,
      ),
  })

const n = (v: string | null | undefined) => String(Number(v ?? 0))

/** FR-INV-013: what to reorder, per vendor; one tap makes a draft PO to check and send. */
export function ReorderTab({ outletId, onDrafted }: { outletId: string; onDrafted: () => void }) {
  const { t, i18n } = useTranslation()
  const list = useSuggestions(outletId, i18n.language)
  return (
    <div className="flex flex-col gap-3">
      <p className="text-sm text-ink-soft">{t('purchasing.reorder.help')}</p>
      {list.error && <Alert>{errorMessage(list.error, t)}</Alert>}
      {list.isSuccess && list.data.length === 0 && (
        <p className="text-ink-soft">{t('purchasing.reorder.empty')}</p>
      )}
      {list.data?.map((g) => (
        <Group key={g.vendor_id ?? 'none'} group={g} outletId={outletId} onDrafted={onDrafted} />
      ))}
    </div>
  )
}

function Group({
  group,
  outletId,
  onDrafted,
}: {
  group: SuggestionGroup
  outletId: string
  onDrafted: () => void
}) {
  const { t } = useTranslation()
  const save = useSaveOrder()
  const lines = group.lines.filter((l) => l.order_qty && l.order_unit_id && l.unit_price != null)
  const draft = () =>
    group.vendor_id &&
    save.mutate(
      {
        body: {
          outlet_id: outletId,
          vendor_id: group.vendor_id,
          order_date: todayIso(),
          lines: lines.map((l) => ({
            item_id: l.item_id,
            qty: l.order_qty as string,
            unit_id: l.order_unit_id as string,
            unit_price: l.unit_price as number,
          })),
        },
      },
      { onSuccess: onDrafted },
    )
  return (
    <Card className="flex flex-col gap-2">
      <h2 className="font-bold">{group.vendor_name ?? t('purchasing.reorder.noVendor')}</h2>
      <ul className="text-sm">
        {group.lines.map((l) => (
          <li key={l.item_id}>
            {t('purchasing.reorder.line', {
              name: l.name,
              have: n(l.on_hand),
              point: n(l.reorder_point),
              need: n(l.suggested),
              unit: l.unit_code,
            })}
          </li>
        ))}
      </ul>
      {save.error ? <Alert>{errorMessage(save.error, t)}</Alert> : null}
      {group.vendor_id && lines.length > 0 && (
        <Button className="self-start" disabled={save.isPending} onClick={draft}>
          {t('purchasing.reorder.draft')}
        </Button>
      )}
    </Card>
  )
}
