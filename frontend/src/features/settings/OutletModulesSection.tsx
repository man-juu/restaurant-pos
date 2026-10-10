import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Alert, Button, Card } from '../../components/ui'
import { request } from '../../lib/api/client'
import type { OutletModulesOut } from '../../lib/api/types'
import { errorMessage } from '../../lib/errors'
import { isOn, type Off, setModule } from './outletModules'
import { SaveBar } from './shared'

const OM = '/api/v1/outlet-modules'

/** Owner 2026-10-10: modules per outlet. Every outlet alike, or some with their own set;
 * a column button applies one module to all outlets at once. */
export function OutletModulesSection({ canEdit }: { canEdit: boolean }) {
  const { t } = useTranslation()
  const data = useQuery({
    queryKey: ['outlet-modules'],
    queryFn: () => request<OutletModulesOut>('GET', OM),
  })
  if (data.error) return <Alert>{errorMessage(data.error, t)}</Alert>
  if (!data.data) return null
  return <Grid key={data.dataUpdatedAt} data={data.data} canEdit={canEdit} />
}

function Grid({ data, canEdit }: { data: OutletModulesOut; canEdit: boolean }) {
  const { t } = useTranslation()
  const client = useQueryClient()
  const [off, setOff] = useState<Off>(() =>
    Object.fromEntries(data.outlets.map((o) => [o.outlet_id, o.off])),
  )
  const save = useMutation({
    mutationFn: () => request<void>('PUT', OM, { off }),
    onSuccess: () =>
      client
        .invalidateQueries({ queryKey: ['outlet-modules'] })
        .then(() => client.invalidateQueries({ queryKey: ['outlets'] })),
  })
  const ids = data.outlets.map((o) => o.outlet_id)
  const flip = (outlets: string[], m: string, on: boolean) =>
    setOff(setModule(off, { outletIds: outlets, module: m, on }, data.depends_on))
  const name = (m: string) => t(`settings.outletModules.names.${m}`, { defaultValue: m })
  return (
    <Card className="flex flex-col gap-3">
      <p className="text-sm text-ink-soft">{t('settings.outletModules.help')}</p>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[560px] text-sm">
          <thead>
            <tr className="text-left">
              <th className="p-2">{t('pos.outlet')}</th>
              {data.modules.map((m) => (
                <ModuleHead
                  key={m}
                  label={name(m)}
                  canEdit={canEdit}
                  onAll={(on) => flip(ids, m, on)}
                />
              ))}
            </tr>
          </thead>
          <tbody>
            {data.outlets.map((o) => (
              <tr key={o.outlet_id} className="border-t border-line">
                <th className="p-2 text-left font-semibold">{o.name}</th>
                {data.modules.map((m) => (
                  <td key={m} className="p-2">
                    <label className="flex min-h-11 min-w-11 items-center justify-center">
                      <input
                        type="checkbox"
                        className="size-5"
                        aria-label={`${name(m)} · ${o.name}`}
                        disabled={!canEdit}
                        checked={isOn(off, o.outlet_id, m)}
                        onChange={(e) => flip([o.outlet_id], m, e.target.checked)}
                      />
                    </label>
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {canEdit && <SaveBar mutation={save} onSave={() => save.mutate()} />}
    </Card>
  )
}

function ModuleHead(p: { label: string; canEdit: boolean; onAll: (on: boolean) => void }) {
  const { t } = useTranslation()
  return (
    <th className="p-2 align-top">
      <span className="block">{p.label}</span>
      {p.canEdit && (
        <span className="flex flex-wrap gap-1">
          <Button variant="ghost" onClick={() => p.onAll(true)}>
            {t('settings.outletModules.allOn')}
          </Button>
          <Button variant="ghost" onClick={() => p.onAll(false)}>
            {t('settings.outletModules.allOff')}
          </Button>
        </span>
      )}
    </th>
  )
}
