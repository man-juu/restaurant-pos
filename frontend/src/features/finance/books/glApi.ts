import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { request } from '../../../lib/api/client'
import type {
  BalanceSheet,
  CashFlow,
  GlAccountOut,
  JournalOut,
  LedgerSetupOut,
  PeriodOut,
  TrialRow,
} from '../../../lib/api/types'

const G = '/api/v1/finance/gl'
/** Query options for one ledger read; every key starts with 'gl' so writes refresh all. */
const read = <T>(key: unknown[], path: string, enabled = true) => ({
  queryKey: ['gl', ...key],
  queryFn: () => request<T>('GET', `${G}${path}`),
  enabled,
})

export const useSetup = () => useQuery(read<LedgerSetupOut | null>(['setup'], '/setup'))
export const useGlAccounts = (enabled = true) =>
  useQuery(read<GlAccountOut[]>(['accounts'], '/accounts', enabled))
export const useJournals = (since: string, until: string) =>
  useQuery(
    read<JournalOut[]>(['journals', since, until], `/journals?since=${since}&until=${until}`),
  )
export const useTrial = (until: string) =>
  useQuery(read<TrialRow[]>(['trial', until], `/trial-balance?until=${until}`))
export const useSheet = (asOf: string) =>
  useQuery(read<BalanceSheet>(['sheet', asOf], `/balance-sheet?as_of=${asOf}`))
export const useCashFlow = (since: string, until: string) =>
  useQuery(read<CashFlow>(['flow', since, until], `/cash-flow?since=${since}&until=${until}`))
export const usePeriods = () => useQuery(read<PeriodOut[]>(['periods'], '/periods'))

/** Any ledger write refreshes every ledger view. */
export function useGlAction() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({
      method = 'POST',
      path,
      body,
    }: {
      method?: 'POST' | 'PUT'
      path: string
      body?: unknown
    }) => request<unknown>(method, `${G}/${path}`, body),
    onSuccess: () => client.invalidateQueries({ queryKey: ['gl'] }),
  })
}
