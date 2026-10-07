import type { Capabilities } from '../lib/api/types'

export interface NavItem {
  key: string
  to: string
}

/** Navigation comes from /me/capabilities: a convenience only, the server checks every call. */
export function navItems(caps: Capabilities | undefined): NavItem[] {
  if (!caps) return [{ key: 'dashboard', to: '/' }]
  const items: NavItem[] = [{ key: 'dashboard', to: '/' }]
  if (caps.permissions.includes('tenant.outlet.view'))
    items.push({ key: 'outlets', to: '/outlets' })
  for (const key of caps.nav) items.push({ key, to: `/${key}` })
  if (caps.permissions.includes('tenant.settings.view'))
    items.push({ key: 'settings', to: '/settings' })
  return items
}
