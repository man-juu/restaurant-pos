import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { TextInput } from '../../../components/form'
import { Alert, Button, Card } from '../../../components/ui'
import type { HomeOut, LocationOut } from '../../../lib/api/types'
import { errorMessage } from '../../../lib/errors'
import { ComponentPicker } from '../../catalog/ComponentPicker'
import { useHomes, useLocationAction, useLocations } from './locationApi'

const STOCK_TYPES = ['ingredient', 'semi_finished', 'menu'] as const

/** FR-INV-017: the outlet's storage places and the items kept in each. */
export function LocationsTab({ outletId, canManage }: { outletId: string; canManage: boolean }) {
  const { t, i18n } = useTranslation()
  const places = useLocations(outletId)
  const homes = useHomes(outletId, i18n.language)
  const action = useLocationAction()
  const [name, setName] = useState('')
  const add = () =>
    action.mutate(
      { method: 'POST', path: 'locations', body: { outlet_id: outletId, name: name.trim() } },
      { onSuccess: () => setName('') },
    )
  return (
    <div className="flex flex-col gap-3">
      {canManage && (
        <div className="flex flex-wrap items-end gap-2">
          <TextInput
            label={t('locations.name')}
            value={name}
            maxLength={80}
            onChange={(e) => setName(e.target.value)}
          />
          <Button onClick={add} disabled={!name.trim() || action.isPending}>
            {t('locations.add')}
          </Button>
        </div>
      )}
      {action.error ? <Alert>{errorMessage(action.error, t)}</Alert> : null}
      {places.isSuccess && places.data.length === 0 && (
        <p className="text-ink-soft">{t('locations.empty')}</p>
      )}
      {places.data?.map((place) => (
        <Place
          key={place.id}
          place={place}
          items={(homes.data ?? []).filter((h) => h.location_id === place.id)}
          canManage={canManage}
        />
      ))}
    </div>
  )
}

function Place({
  place,
  items,
  canManage,
}: {
  place: LocationOut
  items: HomeOut[]
  canManage: boolean
}) {
  const { t } = useTranslation()
  const action = useLocationAction()
  const toggle = () =>
    action.mutate({
      method: 'PUT',
      path: `locations/${place.id}`,
      body: { name: place.name, sort_order: place.sort_order, is_active: !place.is_active },
    })
  return (
    <Card className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className={place.is_active ? 'font-bold' : 'font-bold text-muted'}>{place.name}</h2>
        {canManage && (
          <Button variant="ghost" onClick={toggle} disabled={action.isPending}>
            {t(place.is_active ? 'locations.off' : 'locations.on')}
          </Button>
        )}
      </div>
      <ul className="flex flex-wrap gap-2">
        {items.map((h) => (
          <li
            key={h.item_id}
            className="flex items-center gap-1 rounded-lg border border-line px-2"
          >
            <span>{h.name}</span>
            {canManage && (
              <Button
                variant="ghost"
                aria-label={t('locations.remove', { name: h.name })}
                onClick={() =>
                  action.mutate({
                    method: 'DELETE',
                    path: `locations/homes/${h.item_id}?outlet_id=${place.outlet_id}`,
                  })
                }
              >
                {t('locations.unassign')}
              </Button>
            )}
          </li>
        ))}
      </ul>
      {canManage && place.is_active && (
        <ComponentPicker
          label={t('locations.keep')}
          types={STOCK_TYPES}
          exclude={new Set(items.map((i) => i.item_id))}
          onPick={(item) =>
            action.mutate({
              method: 'PUT',
              path: `locations/${place.id}/items`,
              body: { item_ids: [item.id] },
            })
          }
        />
      )}
      {action.error ? <Alert>{errorMessage(action.error, t)}</Alert> : null}
    </Card>
  )
}
