import { afterEach, describe, expect, it } from 'vitest'

import { resolvedTheme, setAppearance } from './theme'

afterEach(() => setAppearance({ mode: 'system', accent: 'teal', background: 'tide' }))

describe('appearance', () => {
  it('applies mode, accent and background to <html> and remembers them', () => {
    setAppearance({ mode: 'light', accent: 'lavender', background: 'dusk' })
    const root = document.documentElement
    expect(root.dataset.theme).toBe('light')
    expect(root.dataset.accent).toBe('lavender')
    expect(root.style.getPropertyValue('--app-background')).toContain('dusk.svg')
    expect(JSON.parse(localStorage.getItem('pos.appearance') ?? '{}').accent).toBe('lavender')
  })
  it('explicit modes win over the system setting', () => {
    expect(resolvedTheme('dark')).toBe('dark')
    expect(resolvedTheme('light')).toBe('light')
  })
})
