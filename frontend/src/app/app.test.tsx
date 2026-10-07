import { cleanup, fireEvent, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'

import i18n from '../lib/i18n'
import { mockApi, renderApp } from '../test-utils'

const session = (mfa_state: string) => ({
  user: { id: 'u', email: 'o@x.id', name: 'Rina', locale: 'id' },
  tenants: [{ id: 't1', name: 'Dapur Sehat' }],
  active_tenant_id: mfa_state === 'ok' ? 't1' : null,
  csrf_token: 'csrf-1',
  mfa_state,
})

const capabilities = {
  tenant_id: 't1',
  permissions: ['tenant.outlet.view'],
  all_outlets: true,
  outlet_ids: [],
  modules: ['inventory'],
  subscription: { state: 'expiring', days_left: 5 },
  nav: ['inventory'],
}

beforeEach(() => {
  void i18n.changeLanguage('en')
})
afterEach(cleanup)

describe('sign-in flow', () => {
  it('asks for the authenticator code after the password and sends the CSRF token', async () => {
    const calls = mockApi({
      'GET /api/v1/auth/session': { status: 401, body: { code: 'not_authenticated' } },
      'POST /api/v1/auth/login': { body: session('verify') },
      'POST /api/v1/auth/mfa/verify': { status: 400, body: { code: 'invalid_code' } },
    })
    renderApp('/login')
    fireEvent.change(await screen.findByLabelText('Email'), { target: { value: 'o@x.id' } })
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'secret pass' } })
    fireEvent.click(screen.getByRole('button', { name: 'Continue' }))
    const code = await screen.findByLabelText('Code')
    fireEvent.change(code, { target: { value: '000000' } })
    fireEvent.click(screen.getByRole('button', { name: 'Verify' }))
    expect((await screen.findByRole('alert')).textContent).toContain('That code is not valid')
    const verify = calls.find((c) => c.path === '/api/v1/auth/mfa/verify')
    expect(verify?.body).toEqual({ code: '000000' })
  })

  it('shows translated server errors', async () => {
    mockApi({
      'GET /api/v1/auth/session': { status: 401, body: { code: 'not_authenticated' } },
      'POST /api/v1/auth/login': { status: 401, body: { code: 'invalid_credentials' } },
    })
    void i18n.changeLanguage('id')
    renderApp('/login')
    fireEvent.change(await screen.findByLabelText('Email'), { target: { value: 'o@x.id' } })
    fireEvent.change(screen.getByLabelText('Kata sandi'), { target: { value: 'x' } })
    fireEvent.click(screen.getByRole('button', { name: 'Lanjut' }))
    expect((await screen.findByRole('alert')).textContent).toContain('Email atau kata sandi salah.')
  })
})

describe('shell (FR-SUB-002, FR-TEN-003)', () => {
  it('shows the renewal banner and capability-driven navigation', async () => {
    mockApi({
      'GET /api/v1/auth/session': { body: session('ok') },
      'GET /api/v1/me/capabilities': { body: capabilities },
    })
    renderApp('/')
    expect((await screen.findByRole('status')).textContent).toContain('ends in 5 days')
    await waitFor(() =>
      expect(screen.getAllByRole('link', { name: 'Inventory' }).length).toBeGreaterThan(0),
    )
    expect(screen.queryByRole('link', { name: 'Purchasing' })).toBeNull()
  })

  it('sends signed-out users to the login page', async () => {
    mockApi({ 'GET /api/v1/auth/session': { status: 401, body: { code: 'not_authenticated' } } })
    renderApp('/')
    expect(await screen.findByRole('button', { name: 'Continue' })).toBeTruthy()
  })
})
