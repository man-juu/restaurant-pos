import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { SelectInput, TextInput } from '../../components/form'
import { Alert, Button, Card } from '../../components/ui'
import { request } from '../../lib/api/client'
import { errorMessage } from '../../lib/errors'

interface Row {
  id: string
  title_en: string
  level: string
  starts_at: string
  ends_at: string
  tenant_ids: string[]
}

const EMPTY = {
  title_en: '',
  title_id: '',
  body_en: '',
  body_id: '',
  level: 'info',
  starts: '',
  ends: '',
}
const FIELDS = ['title_en', 'title_id', 'body_en', 'body_id'] as const

/** FR-ADM-005: announcements for all businesses, or for the ones listed by id. */
export function AdminAnnouncements() {
  const { t } = useTranslation()
  const client = useQueryClient()
  const list = useQuery({
    queryKey: ['admin-announcements'],
    queryFn: () => request<Row[]>('GET', '/admin-api/announcements'),
  })
  const [f, setF] = useState(EMPTY)
  const [targets, setTargets] = useState('')
  const save = useMutation({
    mutationFn: () =>
      request('POST', '/admin-api/announcements', {
        ...Object.fromEntries(FIELDS.map((k) => [k, f[k].trim()])),
        level: f.level,
        starts_at: new Date(f.starts).toISOString(),
        ends_at: new Date(f.ends).toISOString(),
        tenant_ids: targets.split(/[\s,]+/).filter(Boolean),
      }),
    onSuccess: () => {
      setF(EMPTY)
      return client.invalidateQueries({ queryKey: ['admin-announcements'] })
    },
  })
  const ready = FIELDS.every((k) => f[k].trim()) && f.starts && f.ends
  return (
    <Card className="mt-6 flex flex-col gap-3">
      <h2 className="font-display text-xl font-bold">{t('admin.announce.title')}</h2>
      <div className="grid gap-3 sm:grid-cols-2">
        {FIELDS.map((k) => (
          <TextInput
            key={k}
            label={t(`admin.announce.${k}`)}
            value={f[k]}
            maxLength={k.startsWith('title') ? 120 : 2000}
            onChange={(e) => setF({ ...f, [k]: e.target.value })}
          />
        ))}
        <TextInput
          label={t('admin.announce.starts')}
          type="datetime-local"
          value={f.starts}
          onChange={(e) => setF({ ...f, starts: e.target.value })}
        />
        <TextInput
          label={t('admin.announce.ends')}
          type="datetime-local"
          value={f.ends}
          onChange={(e) => setF({ ...f, ends: e.target.value })}
        />
        <SelectInput
          label={t('admin.announce.level')}
          value={f.level}
          onChange={(e) => setF({ ...f, level: e.target.value })}
        >
          <option value="info">{t('admin.announce.info')}</option>
          <option value="warning">{t('admin.announce.warning')}</option>
        </SelectInput>
        <TextInput
          label={t('admin.announce.targets')}
          value={targets}
          onChange={(e) => setTargets(e.target.value)}
        />
      </div>
      {save.error ? <Alert>{errorMessage(save.error, t)}</Alert> : null}
      <Button
        className="self-start"
        disabled={!ready || save.isPending}
        onClick={() => save.mutate()}
      >
        {t('admin.announce.publish')}
      </Button>
      <ul className="text-sm">
        {list.data?.map((a) => (
          <li key={a.id}>
            {`${a.title_en} · ${a.level} · ${new Date(a.starts_at).toLocaleString()} – ${new Date(a.ends_at).toLocaleString()} · ${
              a.tenant_ids.length
                ? t('admin.announce.some', { count: a.tenant_ids.length })
                : t('admin.announce.all')
            }`}
          </li>
        ))}
      </ul>
    </Card>
  )
}
