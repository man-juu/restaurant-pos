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

/** JSON for data, raw bytes for files (photos), nothing for bodiless requests. */
function encodeBody(body: unknown): { body?: BodyInit; type?: string } {
  if (body === undefined) return {}
  if (body instanceof Blob) return { body, type: 'application/octet-stream' }
  return { body: JSON.stringify(body), type: 'application/json' }
}

async function failure(response: Response): Promise<ApiError> {
  const data: unknown = await response.json().catch(() => null)
  const err = (data ?? {}) as { code?: string; details?: unknown }
  return new ApiError(response.status, err.code ?? 'network_error', err.details)
}

export async function request<T>(
  method: string,
  path: string,
  body?: unknown,
  extraHeaders: Record<string, string> = {},
): Promise<T> {
  const encoded = encodeBody(body)
  const headers: Record<string, string> = { ...extraHeaders, Accept: 'application/json' }
  if (encoded.type) headers['Content-Type'] = encoded.type
  if (!SAFE.has(method) && csrfToken) headers['X-CSRF-Token'] = csrfToken
  const response = await fetch(path, {
    method,
    headers,
    credentials: 'same-origin',
    body: encoded.body,
  })
  if (!response.ok) throw await failure(response)
  if (response.status === 204) return undefined as T
  return (await response.json().catch(() => null)) as T
}
