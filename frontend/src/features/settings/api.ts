import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { request } from '../../lib/api/client'
import type { AllSettings, ApprovalRuleOut, RoleOut } from '../../lib/api/types'

export function useSettings() {
  return useQuery({
    queryKey: ['settings'],
    queryFn: () => request<AllSettings>('GET', '/api/v1/settings'),
  })
}

export function useSaveSetting<K extends keyof AllSettings>(key: K) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (value: AllSettings[K]) =>
      request<AllSettings[K]>('PUT', `/api/v1/settings/${key}`, value),
    onSuccess: () => client.invalidateQueries({ queryKey: ['settings'] }),
  })
}

export function useApprovalRules() {
  return useQuery({
    queryKey: ['approval-rules'],
    queryFn: () => request<ApprovalRuleOut[]>('GET', '/api/v1/approval-rules'),
  })
}

export function useRoles() {
  return useQuery({
    queryKey: ['roles'],
    queryFn: () => request<RoleOut[]>('GET', '/api/v1/roles'),
  })
}

export function useApprovalRuleMutations() {
  const client = useQueryClient()
  const refresh = () => client.invalidateQueries({ queryKey: ['approval-rules'] })
  return {
    create: useMutation({
      mutationFn: (rule: Omit<ApprovalRuleOut, 'id'>) =>
        request<ApprovalRuleOut>('POST', '/api/v1/approval-rules', rule),
      onSuccess: refresh,
    }),
    remove: useMutation({
      mutationFn: (id: string) => request<void>('DELETE', `/api/v1/approval-rules/${id}`),
      onSuccess: refresh,
    }),
  }
}
