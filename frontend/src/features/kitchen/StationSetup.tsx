import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { CheckInput, TextInput } from '../../components/form'
import { Alert, Button, Card } from '../../components/ui'
import { errorMessage } from '../../lib/errors'
import { useCategories } from '../catalog/api'
import { useSaveStation } from './kitchenApi'

/** FR-KDS-002: a station gets the menu categories it makes; the default gets the rest. */
export function StationSetup({ outletId }: { outletId: string }) {
  const { t } = useTranslation()
  const save = useSaveStation()
  const categories = useCategories().data ?? []
  const [name, setName] = useState('')
  const [picked, setPicked] = useState<string[]>([])
  const [isDefault, setDefault] = useState(false)
  const reset = () => (setName(''), setPicked([]), setDefault(false))
  return (
    <Card className="flex flex-col gap-3">
      <h2 className="font-display text-lg font-bold">{t('kitchen.setup')}</h2>
      <TextInput
        label={t('kitchen.stationName')}
        value={name}
        maxLength={60}
        onChange={(e) => setName(e.target.value)}
      />
      <ul className="grid gap-1 sm:grid-cols-3">
        {categories.map((c) => (
          <li key={c.id}>
            <CheckInput
              label={c.name}
              checked={picked.includes(c.id)}
              onChange={(on) =>
                setPicked(on ? [...picked, c.id] : picked.filter((p) => p !== c.id))
              }
            />
          </li>
        ))}
      </ul>
      <CheckInput label={t('kitchen.default')} checked={isDefault} onChange={setDefault} />
      {save.error ? <Alert>{errorMessage(save.error, t)}</Alert> : null}
      <Button
        disabled={!name.trim() || !outletId || save.isPending}
        onClick={() =>
          save.mutate(
            { outlet_id: outletId, name: name.trim(), category_ids: picked, is_default: isDefault },
            { onSuccess: reset },
          )
        }
      >
        {t('kitchen.addStation')}
      </Button>
    </Card>
  )
}
