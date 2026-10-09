import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { TextInput } from '../../components/form'
import { Alert, Button, Card } from '../../components/ui'
import { errorMessage } from '../../lib/errors'
import { useCreateFloor, useCreateTable } from './tablesApi'

/** FR-TBL-001: add floors (areas) and tables with their seats. */
export function TableSetup({ outletId, floorId }: { outletId: string; floorId: string }) {
  const { t } = useTranslation()
  const floor = useCreateFloor()
  const table = useCreateTable()
  const [floorName, setFloorName] = useState('')
  const [name, setName] = useState('')
  const [seats, setSeats] = useState('4')
  const capacity = Number.parseInt(seats, 10)
  return (
    <Card className="flex flex-col gap-3">
      <h2 className="font-display text-lg font-bold">{t('tables.setup')}</h2>
      <div className="flex flex-wrap items-end gap-2">
        <TextInput
          label={t('tables.floorName')}
          value={floorName}
          maxLength={80}
          onChange={(e) => setFloorName(e.target.value)}
        />
        <Button
          variant="ghost"
          disabled={!floorName.trim() || !outletId}
          onClick={() =>
            floor.mutate(
              { outlet_id: outletId, name: floorName.trim() },
              { onSuccess: () => setFloorName('') },
            )
          }
        >
          {t('tables.addFloor')}
        </Button>
      </div>
      {floorId && (
        <div className="flex flex-wrap items-end gap-2">
          <TextInput
            label={t('tables.tableName')}
            value={name}
            maxLength={40}
            onChange={(e) => setName(e.target.value)}
          />
          <TextInput
            label={t('tables.capacity')}
            inputMode="numeric"
            value={seats}
            onChange={(e) => setSeats(e.target.value)}
          />
          <Button
            variant="ghost"
            disabled={!name.trim() || !(capacity >= 1 && capacity <= 100)}
            onClick={() =>
              table.mutate(
                { floor_id: floorId, name: name.trim(), capacity },
                { onSuccess: () => setName('') },
              )
            }
          >
            {t('tables.addTable')}
          </Button>
        </div>
      )}
      {floor.error || table.error ? (
        <Alert>{errorMessage(floor.error ?? table.error, t)}</Alert>
      ) : null}
    </Card>
  )
}
