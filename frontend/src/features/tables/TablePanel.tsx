import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'

import { SelectInput, TextInput } from '../../components/form'
import { Alert, Button, Card } from '../../components/ui'
import type { ChannelOut, TableOut } from '../../lib/api/types'
import { errorMessage } from '../../lib/errors'
import { SessionActions } from './SessionActions'
import { useSeat, useTableStatus } from './tablesApi'

/** The selected table: seat a party, or what the party has (FR-TBL-002, 003). */
export function TablePanel({
  table,
  tables,
  channels,
  money,
}: {
  table: TableOut
  tables: TableOut[]
  channels: ChannelOut[]
  money: (v: number) => string
}) {
  const { t } = useTranslation()
  const session = table.session
  return (
    <Card className="flex flex-col gap-3">
      <h2 className="font-display text-xl font-bold">{table.name}</h2>
      {session ? (
        <>
          <ul className="flex flex-col gap-2">
            {session.orders.map((o) => (
              <li key={o.id} className="flex items-center justify-between gap-2">
                <span>
                  {o.number} · {t(`pos.orderStatus.${o.status}`)} · {money(o.subtotal)}
                </span>
                {o.status === 'open' && (
                  <Link className="font-semibold text-accent underline" to={`/pos?order=${o.id}`}>
                    {t('tables.openOnTill')}
                  </Link>
                )}
              </li>
            ))}
          </ul>
          <SessionActions session={session} table={table} tables={tables} />
        </>
      ) : (
        <FreeTable table={table} channels={channels} />
      )}
    </Card>
  )
}

function FreeTable({ table, channels }: { table: TableOut; channels: ChannelOut[] }) {
  const { t } = useTranslation()
  const status = useTableStatus()
  if (table.status === 'needs_cleaning')
    return (
      <Button onClick={() => status.mutate({ tableId: table.id, status: 'available' })}>
        {t('tables.markClean')}
      </Button>
    )
  return (
    <>
      <SeatForm table={table} channels={channels} />
      <Button
        variant="ghost"
        onClick={() =>
          status.mutate({
            tableId: table.id,
            status: table.status === 'reserved' ? 'available' : 'reserved',
          })
        }
      >
        {t(table.status === 'reserved' ? 'tables.unreserve' : 'tables.reserve')}
      </Button>
      {status.error ? <Alert>{errorMessage(status.error, t)}</Alert> : null}
    </>
  )
}

function SeatForm({ table, channels }: { table: TableOut; channels: ChannelOut[] }) {
  const { t } = useTranslation()
  const seat = useSeat()
  const dineIn = channels.find((c) => c.kind === 'dine_in') ?? channels[0]
  const [channelId, setChannel] = useState(dineIn?.id ?? '')
  const [party, setParty] = useState(String(Math.min(2, table.capacity)))
  const size = Number.parseInt(party, 10)
  const ok = channelId !== '' && size >= 1 && size <= 200
  return (
    <div className="grid gap-2 sm:grid-cols-2">
      <TextInput
        label={t('tables.party')}
        inputMode="numeric"
        value={party}
        onChange={(e) => setParty(e.target.value)}
      />
      <SelectInput
        label={t('pos.channel')}
        value={channelId}
        onChange={(e) => setChannel(e.target.value)}
      >
        {channels.map((c) => (
          <option key={c.id} value={c.id}>
            {c.name}
          </option>
        ))}
      </SelectInput>
      {seat.error ? <Alert>{errorMessage(seat.error, t)}</Alert> : null}
      <Button
        disabled={!ok || seat.isPending}
        onClick={() => seat.mutate({ tableId: table.id, channelId, partySize: size })}
      >
        {t('tables.seat')}
      </Button>
    </div>
  )
}
