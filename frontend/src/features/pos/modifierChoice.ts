import type { MenuItemOut } from '../../lib/api/types'

export type Group = MenuItemOut['modifier_groups'][number]

/** Each group's min and max hold (the server checks again). */
export function choiceValid(groups: Group[], picked: string[]): boolean {
  return groups.every((g) => {
    const n = g.options.filter((o) => picked.includes(o.id)).length
    return n >= (g.min_select ?? 0) && n <= (g.max_select ?? 1)
  })
}
