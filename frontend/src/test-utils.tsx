import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render } from '@testing-library/react'
import type { ReactElement } from 'react'
import { createMemoryRouter, RouterProvider } from 'react-router'

import './lib/i18n'
import { routes } from './app/routes'

export function renderApp(path: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const router = createMemoryRouter(routes, { initialEntries: [path] })
  return render(
    <QueryClientProvider client={client}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  )
}

/** Replace fetch with a table of path -> response. */
export function mockApi(table: Record<string, { status?: number; body?: unknown }>) {
  const calls: { method: string; path: string; body: unknown }[] = []
  globalThis.fetch = (async (input: string, init?: RequestInit) => {
    const method = init?.method ?? 'GET'
    calls.push({
      method,
      path: input,
      body: init?.body ? JSON.parse(String(init.body)) : undefined,
    })
    const hit = table[`${method} ${input}`] ?? { status: 404, body: { code: 'not_found' } }
    return new Response(hit.body === undefined ? null : JSON.stringify(hit.body), {
      status: hit.status ?? 200,
      headers: { 'Content-Type': 'application/json' },
    })
  }) as typeof fetch
  return calls
}

export type { ReactElement }
