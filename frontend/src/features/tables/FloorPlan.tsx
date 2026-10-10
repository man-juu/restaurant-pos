import { clsx } from 'clsx'
import { type KeyboardEvent, type PointerEvent, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Alert } from '../../components/ui'
import type { TableOut } from '../../lib/api/types'
import { errorMessage } from '../../lib/errors'
import { useMoveTable } from './tablesApi'

export const COLS = 24
export const ROWS = 16
const SIZE = 2 // a table takes 2 x 2 cells
const ARROWS: Record<string, [number, number]> = {
  ArrowLeft: [-1, 0],
  ArrowRight: [1, 0],
  ArrowUp: [0, -1],
  ArrowDown: [0, 1],
}
const TONE: Record<string, string> = {
  available: 'bg-card',
  occupied: 'bg-accent text-on-accent',
  reserved: 'bg-raised',
  needs_cleaning: 'bg-danger/20',
}

const clamp = (v: number, max: number) => Math.min(Math.max(v, 0), max)

type Props = {
  tables: TableOut[]
  editing: boolean
  selected?: string
  onSelect: (id: string) => void
}

/** FR-TBL-009: the floor as a plan. In edit mode, drag a table (or use the arrow keys) to
 *  place it; the spot is saved when it is dropped. */
export function FloorPlan({ tables, editing, selected, onSelect }: Props) {
  const { t } = useTranslation()
  const box = useRef<HTMLDivElement>(null)
  const move = useMoveTable()
  const [drag, setDrag] = useState<{ id: string; x: number; y: number }>()
  const cellAt = (e: PointerEvent) => {
    const r = box.current?.getBoundingClientRect()
    if (!r) return { x: 0, y: 0 }
    const x = Math.floor(((e.clientX - r.left) / r.width) * COLS) - SIZE / 2
    const y = Math.floor(((e.clientY - r.top) / r.height) * ROWS) - SIZE / 2
    return { x: clamp(x, COLS - SIZE), y: clamp(y, ROWS - SIZE) }
  }
  const drop = (table: TableOut, x: number, y: number) => {
    setDrag(undefined)
    if (x !== table.x || y !== table.y) move.mutate({ table, x, y })
  }
  const key = (table: TableOut, e: KeyboardEvent) => {
    const step = ARROWS[e.key]
    if (!editing || !step) return
    e.preventDefault()
    drop(table, clamp(table.x + step[0], COLS - SIZE), clamp(table.y + step[1], ROWS - SIZE))
  }
  return (
    <div className="flex flex-col gap-2">
      {editing && <p className="text-sm text-ink-soft">{t('tables.plan.help')}</p>}
      <div
        ref={box}
        className={clsx(
          'relative aspect-[3/2] w-full touch-none rounded-xl border border-line bg-ground',
          editing &&
            '[background-image:radial-gradient(var(--line)_1px,transparent_1px)] [background-size:4.1667%_6.25%]',
        )}
        onPointerMove={(e) => drag && setDrag({ id: drag.id, ...cellAt(e) })}
      >
        {tables.map((table) => {
          const at = drag?.id === table.id ? drag : table
          return (
            <button
              key={table.id}
              type="button"
              aria-pressed={selected === table.id}
              aria-label={t('tables.plan.table', { name: table.name, seats: table.capacity })}
              className={clsx(
                'absolute flex flex-col items-center justify-center rounded-lg border text-sm font-bold',
                TONE[table.status] ?? 'bg-card',
                selected === table.id ? 'border-accent ring-2 ring-accent' : 'border-line-strong',
                editing && 'cursor-grab',
              )}
              style={{
                left: `${(at.x / COLS) * 100}%`,
                top: `${(at.y / ROWS) * 100}%`,
                width: `${(SIZE / COLS) * 100}%`,
                height: `${(SIZE / ROWS) * 100}%`,
              }}
              onClick={() => onSelect(table.id)}
              onKeyDown={(e) => key(table, e)}
              onPointerDown={(e) => {
                if (!editing) return
                e.currentTarget.setPointerCapture(e.pointerId)
                setDrag({ id: table.id, x: table.x, y: table.y })
              }}
              onPointerUp={() => drag?.id === table.id && drop(table, drag.x, drag.y)}
            >
              {table.name}
              <span className="text-xs font-normal">{table.capacity}</span>
            </button>
          )
        })}
      </div>
      {move.error && <Alert>{errorMessage(move.error, t)}</Alert>}
    </div>
  )
}
