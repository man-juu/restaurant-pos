/**
 * Appearance preferences: mode (system, dark, light), accent swatch and background image.
 * Stored per device; account-level sync can follow once user preferences exist server-side.
 */
import { useSyncExternalStore } from 'react'

export const MODES = ['system', 'dark', 'light'] as const
export const ACCENTS = ['teal', 'sage', 'lavender', 'sky', 'sand'] as const
export const BACKGROUNDS = ['tide', 'mist', 'dusk', 'leaf'] as const

export type Mode = (typeof MODES)[number]
export type Accent = (typeof ACCENTS)[number]
export type Background = (typeof BACKGROUNDS)[number]

export interface Appearance {
  mode: Mode
  accent: Accent
  background: Background
}

const KEY = 'pos.appearance'
const DEFAULT: Appearance = { mode: 'system', accent: 'teal', background: 'tide' }

function read(): Appearance {
  try {
    const raw = JSON.parse(localStorage.getItem(KEY) ?? '{}') as Partial<Appearance>
    return {
      mode: MODES.includes(raw.mode as Mode) ? (raw.mode as Mode) : DEFAULT.mode,
      accent: ACCENTS.includes(raw.accent as Accent) ? (raw.accent as Accent) : DEFAULT.accent,
      background: BACKGROUNDS.includes(raw.background as Background)
        ? (raw.background as Background)
        : DEFAULT.background,
    }
  } catch {
    return DEFAULT // blocked storage or bad JSON: defaults still render correctly
  }
}

let current = read()
const listeners = new Set<() => void>()
const dark =
  typeof window !== 'undefined' ? window.matchMedia?.('(prefers-color-scheme: dark)') : null

export function resolvedTheme(mode: Mode): 'dark' | 'light' {
  if (mode !== 'system') return mode
  return dark && !dark.matches ? 'light' : 'dark'
}

function apply(): void {
  const root = document.documentElement
  root.dataset.theme = resolvedTheme(current.mode)
  root.dataset.accent = current.accent
  root.style.setProperty('--app-background', `url('/backgrounds/${current.background}.svg')`)
  document
    .querySelector('meta[name="theme-color"]')
    ?.setAttribute('content', resolvedTheme(current.mode) === 'dark' ? '#0f151c' : '#eef2f5')
}

export function setAppearance(change: Partial<Appearance>): void {
  current = { ...current, ...change }
  try {
    localStorage.setItem(KEY, JSON.stringify(current))
  } catch {
    // preference only
  }
  apply()
  listeners.forEach((listener) => listener())
}

export function useAppearance(): Appearance {
  return useSyncExternalStore(
    (listener) => {
      listeners.add(listener)
      return () => listeners.delete(listener)
    },
    () => current,
  )
}

if (typeof document !== 'undefined') {
  apply()
  dark?.addEventListener?.('change', () => current.mode === 'system' && apply())
}
