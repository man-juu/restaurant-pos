import { describe, expect, it } from 'vitest'

import { ascii, columns, Receipt } from './escpos'

describe('ESC/POS encoder (FR-SAL-010)', () => {
  it('keeps plain ASCII and drops accents', () => {
    expect(ascii('Café Rp 27.500 ✓')).toBe('Cafe Rp 27.500 ?')
  })

  it('pads left and right text to the paper width', () => {
    expect(columns('Nasi goreng', '25.000', 20)).toBe('Nasi goreng   25.000')
    expect(columns('A very long item name here', '9', 10)).toBe('A very l 9')
  })

  it('starts with initialise and ends with feed and cut', () => {
    const bytes = new Receipt(32).line('Hi').cut()
    expect([...bytes.slice(0, 2)]).toEqual([0x1b, 0x40])
    expect([...bytes.slice(-6)]).toEqual([0x1b, 0x64, 4, 0x1d, 0x56, 0])
  })
})
