import { describe, expect, it } from 'vitest'

import { REPORTS, reportUrl } from './catalog'

describe('report urls', () => {
  it('carries the range, outlet, language, options and format', () => {
    const def = REPORTS.find((r) => r.key === 'salesByItem')!
    const url = reportUrl(
      def,
      { from: '2026-03-01', to: '2026-03-31', outletId: 'o1', lang: 'id-ID' },
      'csv',
    )
    expect(url).toBe(
      '/api/v1/sales/reports/breakdown?from=2026-03-01&to=2026-03-31&lang=id&format=csv&by=item&outlet_id=o1',
    )
  })
  it('leaves the outlet out for all outlets', () => {
    const def = REPORTS.find((r) => r.key === 'stockWaste')!
    expect(reportUrl(def, { from: 'a', to: 'b', outletId: '', lang: 'en' })).not.toContain(
      'outlet_id',
    )
  })
})
