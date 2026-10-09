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
  flags: [],
  currency: 'IDR',
  language: 'id',
  ...over,
})

describe('capability-driven navigation (FR-TEN-003)', () => {
  it('shows only what the server says the user can use', () => {
    expect(navItems(caps({})).map((i) => i.key)).toEqual(['dashboard'])
    const full = caps({ permissions: ['tenant.outlet.view'], nav: ['inventory'] })
    expect(navItems(full).map((i) => i.key)).toEqual(['dashboard', 'outlets', 'inventory'])
  })

  it('adds one Reports entry when any report permission applies (FR-RPT-006)', () => {
    const reader = caps({
      permissions: ['sales.report.view', 'inventory.report.view'],
      nav: ['sales'],
    })
    expect(navItems(reader).map((i) => i.key)).toEqual(['dashboard', 'sales', 'reports'])
  })
})
