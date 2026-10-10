import type { CategoryOut } from '../../lib/api/types'

export interface TreeRow {
  row: CategoryOut
  depth: number
}

/** Depth-first order with indent levels, so children appear under their parent. */
export function treeOrder(rows: CategoryOut[]): TreeRow[] {
  const byParent = new Map<string | null, CategoryOut[]>()
  for (const row of rows) {
    const key = row.parent_id ?? null
    byParent.set(key, [...(byParent.get(key) ?? []), row])
  }
  const out: TreeRow[] = []
  const visit = (parent: string | null, depth: number) => {
    for (const row of byParent.get(parent) ?? []) {
      out.push({ row, depth })
      if (depth < 20) visit(row.id, depth + 1) // the server caps depth at 20 as well
    }
  }
  visit(null, 0)
  return out
}
