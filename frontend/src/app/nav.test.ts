import { describe, expect, it } from 'vitest'

import type { Capabilities } from '../lib/api/types'
import { navItems } from './nav'

const caps = (over: Partial<Capabilities>): Capabilities => ({
  tenant_id: 't',
  permissions: [],
  all_outlets: true,
  outlet_ids: [],
  modules: [],
  subscription: { state: 'active', days_left: null },
  nav: [],
  ...over,
})

describe('capability-driven navigation (FR-TEN-003)', () => {
  it('shows only what the server says the user can use', () => {
    expect(navItems(caps({})).map((i) => i.key)).toEqual(['dashboard'])
    const full = caps({ permissions: ['tenant.outlet.view'], nav: ['inventory'] })
    expect(navItems(full).map((i) => i.key)).toEqual(['dashboard', 'outlets', 'inventory'])
  })
})
