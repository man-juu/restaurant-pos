import { describe, expect, it } from 'vitest'

import { isOn, setModule } from './outletModules'

const deps = { inventory: [], sales: ['inventory'], tables: ['sales'], finance: ['sales'] }

describe('per-outlet module switches', () => {
  it('turning a module off also turns off what needs it', () => {
    const off = setModule({}, { outletIds: ['a'], module: 'sales', on: false }, deps)
    expect(off.a).toEqual(['finance', 'sales', 'tables'])
    expect(isOn(off, 'a', 'inventory')).toBe(true)
  })
  it('turning a module on brings what it needs, for every picked outlet', () => {
    const start = { a: ['inventory', 'sales', 'tables'], b: ['inventory', 'sales', 'tables'] }
    const off = setModule(start, { outletIds: ['a', 'b'], module: 'tables', on: true }, deps)
    expect(off).toEqual({ a: [], b: [] })
  })
})
