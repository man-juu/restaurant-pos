import type { TFunction } from 'i18next'

import { ApiError } from './api/client'

/** The API returns translation keys ("errors.<code>"); unknown codes get a generic message. */
export function errorMessage(error: unknown, t: TFunction): string {
  const code = error instanceof ApiError ? error.code : 'network_error'
  const key = `errors.${code}`
  return t(key, { defaultValue: t('errors.generic') })
}
