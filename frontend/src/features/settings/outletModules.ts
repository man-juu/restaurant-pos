/** Per-outlet module switches (FR-TEN-003): which modules are OFF at each outlet. Switching
 * one keeps the dependency rule the server checks: on brings what it needs, off takes down
 * what needs it. */
export type Off = Record<string, string[]>

function needsOf(module: string, deps: Record<string, string[]>): string[] {
  const out = new Set<string>()
  const walk = (m: string) =>
    (deps[m] ?? []).forEach((d) => {
      if (out.has(d)) return
      out.add(d)
      walk(d)
    })
  walk(module)
  return [...out]
}

function usersOf(module: string, deps: Record<string, string[]>): string[] {
  return Object.keys(deps).filter((m) => m !== module && needsOf(m, deps).includes(module))
}

export interface Change {
  outletIds: string[]
  module: string
  on: boolean
}

export function setModule(
  off: Off,
  { outletIds, module, on }: Change,
  deps: Record<string, string[]>,
): Off {
  const touched = on ? [module, ...needsOf(module, deps)] : [module, ...usersOf(module, deps)]
  const next: Off = { ...off }
  for (const id of outletIds) {
    const set = new Set(next[id] ?? [])
    touched.forEach((m) => (on ? set.delete(m) : set.add(m)))
    next[id] = [...set].sort()
  }
  return next
}

export const isOn = (off: Off, outletId: string, module: string) =>
  !(off[outletId] ?? []).includes(module)
