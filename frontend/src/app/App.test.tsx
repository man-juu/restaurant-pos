import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import '../lib/i18n'
import { App } from './App'

describe('App', () => {
  it('renders the translated title (FR-X-001)', () => {
    render(<App />)
    expect(screen.getByRole('heading', { name: 'Restaurant POS' })).toBeDefined()
  })
})
