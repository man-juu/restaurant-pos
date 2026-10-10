import { describe, expect, it } from 'vitest'

import en from './en/common.json'
import id from './id/common.json'

const keys = (obj: object, prefix = ''): string[] =>
  Object.entries(obj).flatMap(([k, v]) =>
    typeof v === 'object' && v !== null ? keys(v as object, `${prefix}${k}.`) : [`${prefix}${k}`],
  )

describe('locales (FR-X-001)', () => {
  it('EN and ID have the same keys', () => {
    expect(keys(id).sort()).toEqual(keys(en).sort())
  })
})
