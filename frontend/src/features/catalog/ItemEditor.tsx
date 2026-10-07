import { useTranslation } from 'react-i18next'

import { Alert, Button } from '../../components/ui'
import { errorMessage } from '../../lib/errors'
import { useItem } from './api'
import { ItemForm } from './ItemForm'
import { PricesPanel } from './PricesPanel'
import { RecipePanel } from './RecipePanel'

export function ItemEditor({
  itemId,
  canEdit,
  currency,
  onSaved,
  onClose,
}: {
  itemId?: string
  canEdit: boolean
  currency: string
  onSaved: (id: string) => void
  onClose: () => void
}) {
  const { t, i18n } = useTranslation()
  const item = useItem(itemId, i18n.language)
  const loading = Boolean(itemId) && !item.data

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-center gap-3">
        <Button variant="ghost" onClick={onClose}>
          {t('catalog.back')}
        </Button>
        <h1 className="font-display text-3xl font-extrabold">
          {item.data?.name ?? t('catalog.items.new')}
        </h1>
      </div>
      {item.error && <Alert>{errorMessage(item.error, t)}</Alert>}
      {!loading && (
        // Remount on a new version so the form shows exactly what the server saved.
        <ItemForm
          key={item.data ? `${item.data.id}-${item.data.version}` : 'new'}
          item={item.data}
          canEdit={canEdit}
          onSaved={onSaved}
        />
      )}
      {item.data && item.data.type !== 'ingredient' && (
        <RecipePanel item={item.data} canEdit={canEdit} currency={currency} />
      )}
      {item.data && <PricesPanel itemId={item.data.id} canEdit={canEdit} currency={currency} />}
    </div>
  )
}
