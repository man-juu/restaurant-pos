import { useEffect, useState } from 'react'

import { useOutlets } from '../../lib/session'
import { useChannels } from '../catalog/api'
import { useFloors, useTables } from './tablesApi'

function usePick(first: string | undefined) {
  const [picked, setPicked] = useState('')
  return [picked || first || '', setPicked] as const
}

/** A clock for "seated 25 min" that ticks once a minute. */
export function useNow() {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 60_000)
    return () => clearInterval(id)
  }, [])
  return now
}

/** Outlet, floor and the tables on it, for the floor screen. */
export function useFloorView() {
  const outlets = (useOutlets('tables').data ?? []).filter((o) => o.is_active)
  const [outletId, setOutlet] = usePick(outlets[0]?.id)
  const floors = useFloors(outletId).data ?? []
  const [floorId, setFloor] = usePick(floors[0]?.id)
  const tables = useTables(outletId)
  const all = tables.data ?? []
  return {
    outlets,
    outletId,
    setOutlet,
    floors,
    floorId,
    setFloor,
    tables,
    all,
    shown: all.filter((x) => x.floor_id === floorId && x.is_active),
    channels: useChannels().data ?? [],
  }
}

export type FloorView = ReturnType<typeof useFloorView>
