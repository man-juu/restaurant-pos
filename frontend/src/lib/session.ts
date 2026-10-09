import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { ApiError, request, setCsrfToken } from './api/client'
import type {
  ThisDeviceOut,
  Providers,
  Capabilities,
  MfaSetupOut,
  OutletOut,
  RecoveryCodesOut,
  SessionInfo,
} from './api/types'

const SESSION_KEY = ['session'] as const

async function fetchSession(): Promise<SessionInfo | null> {
  try {
    const session = await request<SessionInfo>('GET', '/api/v1/auth/session')
    setCsrfToken(session.csrf_token)
    return session
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) {
      setCsrfToken(null)
      return null // signed out is a normal state, not an error
    }
    throw error
  }
}

export function useSession() {
  return useQuery({ queryKey: SESSION_KEY, queryFn: fetchSession, staleTime: 60_000 })
}

/** Any call that returns a fresh SessionInfo (login, 2FA, tenant switch) updates the cache. */
function useSessionMutation<V>(fn: (vars: V) => Promise<SessionInfo>) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: fn,
    onSuccess: (session) => {
      setCsrfToken(session.csrf_token)
      client.setQueryData(SESSION_KEY, session)
      void client.invalidateQueries({ queryKey: ['capabilities'] })
    },
  })
}

export const useLogin = () =>
  useSessionMutation((vars: { email: string; password: string }) =>
    request<SessionInfo>('POST', '/api/v1/auth/login', vars),
  )

/** FR-IDN-004: PIN sign-in on a registered device. */
export const usePinLogin = () =>
  useSessionMutation((vars: { user_id: string; pin: string }) =>
    request<SessionInfo>('POST', '/api/v1/auth/pin-login', vars),
  )

/** The registered device this browser is (404 when it is not one). */
export const useThisDevice = () =>
  useQuery({
    queryKey: ['this-device'],
    queryFn: () => request<ThisDeviceOut>('GET', '/api/v1/auth/device'),
    retry: false,
    staleTime: 60_000,
  })

/** Extra sign-in buttons the server has switched on (ADR 0.57). */
export const useProviders = () =>
  useQuery({
    queryKey: ['auth-providers'],
    queryFn: () => request<Providers>('GET', '/api/v1/auth/providers'),
    staleTime: 5 * 60_000,
  })

export const useVerifyMfa = () =>
  useSessionMutation((vars: { code: string }) =>
    request<SessionInfo>('POST', '/api/v1/auth/mfa/verify', vars),
  )

export const useSwitchTenant = () =>
  useSessionMutation((vars: { tenant_id: string }) =>
    request<SessionInfo>('POST', '/api/v1/auth/switch-tenant', vars),
  )

export const useMfaSetup = () =>
  useMutation({ mutationFn: () => request<MfaSetupOut>('POST', '/api/v1/auth/mfa/setup') })

export function useMfaConfirm() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (vars: { code: string }) =>
      request<RecoveryCodesOut>('POST', '/api/v1/auth/mfa/confirm', vars),
    // The session was rotated: reload it after the user has saved the recovery codes.
    onSuccess: () => undefined,
    onSettled: () => client.invalidateQueries({ queryKey: ['capabilities'] }),
  })
}

export function useLogout() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: () => request<void>('POST', '/api/v1/auth/logout'),
    onSettled: () => {
      setCsrfToken(null)
      client.setQueryData(SESSION_KEY, null)
      client.removeQueries({ queryKey: ['capabilities'] })
    },
  })
}

export function useCapabilities(enabled: boolean) {
  return useQuery({
    queryKey: ['capabilities'],
    queryFn: () => request<Capabilities>('GET', '/api/v1/me/capabilities'),
    enabled,
    staleTime: 60_000,
  })
}

export function useOutlets() {
  return useQuery({
    queryKey: ['outlets'],
    queryFn: () => request<OutletOut[]>('GET', '/api/v1/outlets'),
  })
}

export function useReloadSession() {
  const client = useQueryClient()
  return () => client.invalidateQueries({ queryKey: SESSION_KEY })
}
