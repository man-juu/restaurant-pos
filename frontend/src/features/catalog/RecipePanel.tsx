import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Alert, Button, Card, StateBadge } from '../../components/ui'
import type { BomSummary, ItemOut } from '../../lib/api/types'
import { errorMessage } from '../../lib/errors'
import { formatDate, intlLocale } from '../../lib/format'
import { CostingView } from './CostingView'
import { useBom, useBoms, useCosting } from './recipeApi'
import { RecipeEditor } from './RecipeEditor'

/** FR-CAT-005 to 007: recipe versions, the open draft and today's costing. */
export function RecipePanel({
  item,
  canEdit,
  currency,
}: {
  item: ItemOut
  canEdit: boolean
  currency: string
}) {
  const { t, i18n } = useTranslation()
  const boms = useBoms(item.id)
  const costing = useCosting(item.id, i18n.language)
  const versions = boms.data ?? []
  const openDraft = versions.find((b) => b.status === 'draft')
  const current = versions.find((b) => b.id === costing.data?.bom_id)
  const [starting, setStarting] = useState(false)

  return (
    <Card className="flex flex-col gap-4">
      <h2 className="font-display text-xl font-extrabold">{t('catalog.recipe.title')}</h2>
      <p className="text-sm text-ink-soft">{t('catalog.recipe.help')}</p>
      {boms.error && <Alert>{errorMessage(boms.error, t)}</Alert>}
      <VersionList versions={versions} locale={intlLocale(i18n.language)} />
      <CostingSection costing={costing} currency={currency} />
      {canEdit && (
        <DraftSlot
          item={item}
          draftId={openDraft?.id}
          copyId={starting ? current?.id : undefined}
          starting={starting}
          onStart={() => setStarting(true)}
          onClose={() => setStarting(false)}
        />
      )}
    </Card>
  )
}

function CostingSection({
  costing,
  currency,
}: {
  costing: ReturnType<typeof useCosting>
  currency: string
}) {
  const { t } = useTranslation()
  if (costing.error) return <Alert>{errorMessage(costing.error, t)}</Alert>
  if (!costing.data) return null
  if (costing.data.bom_id === null)
    return <p className="text-ink-soft">{t('catalog.recipe.none')}</p>
  return <CostingView costing={costing.data} currency={currency} />
}

function VersionList({ versions, locale }: { versions: BomSummary[]; locale: string }) {
  const { t } = useTranslation()
  const range = (b: BomSummary) =>
    b.valid_from
      ? t(b.valid_to ? 'catalog.recipe.range' : 'catalog.recipe.since', {
          from: formatDate(b.valid_from, locale),
          to: b.valid_to ? formatDate(b.valid_to, locale) : '',
        })
      : ''
  return (
    <ul className="flex flex-wrap gap-2">
      {versions.map((b) => (
        <li
          key={b.id}
          className="flex items-center gap-2 rounded-xl border border-line px-3 py-1.5 text-sm"
        >
          <b>{`v${b.version}`}</b>
          <StateBadge
            state={b.status === 'active' ? 'active' : 'expiring'}
            label={t(`catalog.recipe.status.${b.status}`)}
          />
          <span className="text-ink-soft">{range(b)}</span>
        </li>
      ))}
    </ul>
  )
}

/** One draft at a time: edit the open draft, or start one from the current recipe. */
function DraftSlot({
  item,
  draftId,
  copyId,
  starting,
  onStart,
  onClose,
}: {
  item: ItemOut
  draftId?: string
  copyId?: string
  starting: boolean
  onStart: () => void
  onClose: () => void
}) {
  const { t, i18n } = useTranslation()
  const draft = useBom(draftId, i18n.language)
  const copy = useBom(copyId, i18n.language)
  if (draftId)
    return draft.data ? (
      <RecipeEditor key={draft.data.id} item={item} draft={draft.data} onClose={onClose} />
    ) : null
  if (!starting)
    return (
      <div>
        <Button onClick={onStart}>{t('catalog.recipe.newVersion')}</Button>
      </div>
    )
  if (copyId && !copy.data) return null // wait for the lines to copy
  return <RecipeEditor item={item} copyOf={copy.data} onClose={onClose} />
}
