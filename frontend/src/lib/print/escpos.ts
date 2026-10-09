/**
 * A tiny ESC/POS encoder for 58 and 80 mm thermal printers (FR-SAL-010). Only the commands
 * every cheap Bluetooth printer understands: initialise, bold, centre, feed and cut.
 * Text is reduced to plain ASCII (accents dropped), because printer code pages differ.
 */
const ESC = 0x1b
const GS = 0x1d

export const COLUMNS: Record<number, number> = { 58: 32, 80: 48 }

export function ascii(text: string): string {
  return text
    .normalize('NFKD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/[\u00a0\u202f]/g, ' ')
    .replace(/[^\x20-\x7e]/g, '?')
}

/** Left text and right text on one line of `width` characters (left is cut if needed). */
export function columns(left: string, right: string, width: number): string {
  const r = ascii(right)
  const room = Math.max(1, width - r.length - 1)
  const l = ascii(left).slice(0, room)
  return l + ' '.repeat(width - l.length - r.length) + r
}

export class Receipt {
  private bytes: number[] = [ESC, 0x40] // initialise
  readonly width: number

  constructor(width: number) {
    this.width = width
  }

  line(text = ''): this {
    for (const ch of ascii(text).slice(0, this.width)) this.bytes.push(ch.charCodeAt(0))
    this.bytes.push(0x0a)
    return this
  }

  pair(left: string, right: string): this {
    return this.line(columns(left, right, this.width))
  }

  bold(on: boolean): this {
    this.bytes.push(ESC, 0x45, on ? 1 : 0)
    return this
  }

  center(on: boolean): this {
    this.bytes.push(ESC, 0x61, on ? 1 : 0)
    return this
  }

  rule(): this {
    return this.line('-'.repeat(this.width))
  }

  /** Feed a few lines and cut (printers without a cutter just feed). */
  cut(): Uint8Array {
    this.bytes.push(ESC, 0x64, 4, GS, 0x56, 0x00)
    return Uint8Array.from(this.bytes)
  }
}
