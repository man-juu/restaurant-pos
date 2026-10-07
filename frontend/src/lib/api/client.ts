/**
 * Minimal typed fetch wrapper. Types come from the generated OpenAPI files (tenant.d.ts,
 * admin.d.ts); never hand-write API types. The session cookie is HttpOnly, so JavaScript
 * never sees it; the CSRF token comes from the session response and is kept in memory only.
 */

export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly details: unknown

  constructor(status: number, code: string, details: unknown) {
    super(code)
    this.status = status
    this.code = code
    this.details = details
  }
}

let csrfToken: string | null = null

export function setCsrfToken(token: string | null): void {
  csrfToken = token
}

const SAFE = new Set(['GET', 'HEAD', 'OPTIONS'])

export async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = { Accept: 'application/json' }
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  if (!SAFE.has(method) && csrfToken) headers['X-CSRF-Token'] = csrfToken
  const response = await fetch(path, {
    method,
    headers,
    credentials: 'same-origin',
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  if (response.status === 204) return undefined as T
  const data: unknown = await response.json().catch(() => null)
  if (!response.ok) {
    const err = (data ?? {}) as { code?: string; details?: unknown }
    throw new ApiError(response.status, err.code ?? 'network_error', err.details)
  }
  return data as T
}
