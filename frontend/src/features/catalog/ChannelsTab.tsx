import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { CheckInput, SelectInput, TextInput } from '../../components/form'
import { Alert, Button, Card } from '../../components/ui'
import type { ChannelIn, ChannelOut } from '../../lib/api/types'
import { errorMessage } from '../../lib/errors'
import { SaveBar } from '../settings/shared'
import { useChannels, useSaveChannel } from './api'
import { EditableRow } from './EditableRow'
import { CHANNEL_KINDS } from './labels'

const SLUG = /^[a-z0-9_]{1,40}$/
const NEW_CHANNEL: ChannelIn = {
  code: '',
  name: '',
  kind: 'dine_in',
  platform: null,
  sort_order: 0,
  is_active: true,
}

/** Only the writable fields: the API refuses unknown ones such as `id`. */
function toChannelIn(c?: ChannelOut): ChannelIn {
  if (!c) return NEW_CHANNEL
  const { code, name, kind, platform, sort_order, is_active } = c
  return { code, name, kind, platform, sort_order, is_active }
}

export function ChannelsTab({ canEdit }: { canEdit: boolean }) {
  const { t } = useTranslation()
  const channels = useChannels(true)
  const [editing, setEditing] = useState<ChannelOut | 'new'>()

  return (
    <div className="flex flex-col gap-4">
      <p className="text-sm text-ink-soft">{t('catalog.channels.help')}</p>
      {channels.error && <Alert>{errorMessage(channels.error, t)}</Alert>}
      {channels.isSuccess && channels.data.length === 0 && (
        <p className="text-ink-soft">{t('catalog.channels.empty')}</p>
      )}
      <ul className="grid grid-cols-1 gap-2 lg:grid-cols-2">
        {channels.data?.map((c) => (
          <EditableRow
            key={c.id}
            archived={!c.is_active}
            onEdit={canEdit ? () => setEditing(c) : undefined}
          >
            <b>{c.name}</b>{' '}
            <span className="text-sm text-muted">{t(`catalog.kinds.${c.kind}`)}</span>
          </EditableRow>
        ))}
      </ul>
      {canEdit && !editing && (
        <div>
          <Button onClick={() => setEditing('new')}>{t('catalog.channels.new')}</Button>
        </div>
      )}
      {editing && (
        <ChannelForm
          key={editing === 'new' ? 'new' : editing.id}
          channel={editing === 'new' ? undefined : editing}
          onDone={() => setEditing(undefined)}
        />
      )}
    </div>
  )
}

function ChannelForm({ channel, onDone }: { channel?: ChannelOut; onDone: () => void }) {
  const { t } = useTranslation()
  const save = useSaveChannel()
  const [d, setD] = useState(() => toChannelIn(channel))
  const set = (patch: Partial<ChannelIn>) => setD((old) => ({ ...old, ...patch }))
  const isPlatform = d.kind === 'platform'
  const valid =
    SLUG.test(d.code) && d.name.trim() !== '' && (!isPlatform || SLUG.test(d.platform ?? ''))
  const body: ChannelIn = { ...d, name: d.name.trim(), platform: isPlatform ? d.platform : null }

  return (
    <Card className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4 lg:items-end">
      <TextInput
        label={t('catalog.channels.name')}
        value={d.name}
        maxLength={80}
        onChange={(e) => set({ name: e.target.value })}
      />
      <TextInput
        label={t('catalog.channels.code')}
        value={d.code}
        maxLength={40}
        // Settings and sales refer to the code, so it is fixed once saved.
        disabled={Boolean(channel)}
        invalid={d.code !== '' && !SLUG.test(d.code)}
        onChange={(e) => set({ code: e.target.value.toLowerCase() })}
      />
      <SelectInput
        label={t('catalog.channels.kind')}
        value={d.kind}
        onChange={(e) => set({ kind: e.target.value as ChannelIn['kind'] })}
      >
        {CHANNEL_KINDS.map((k) => (
          <option key={k} value={k}>
            {t(`catalog.kinds.${k}`)}
          </option>
        ))}
      </SelectInput>
      {isPlatform && (
        <TextInput
          label={t('catalog.channels.platform')}
          value={d.platform ?? ''}
          maxLength={40}
          onChange={(e) => set({ platform: e.target.value.toLowerCase() })}
        />
      )}
      <CheckInput
        label={t('catalog.item.active')}
        checked={d.is_active ?? true}
        onChange={(v) => set({ is_active: v })}
      />
      <div className="flex flex-wrap gap-3 sm:col-span-2 lg:col-span-4">
        <SaveBar
          mutation={save}
          disabled={!valid}
          onSave={() => save.mutate({ id: channel?.id, body }, { onSuccess: onDone })}
        />
        <Button variant="ghost" onClick={onDone}>
          {t('catalog.cancel')}
        </Button>
      </div>
    </Card>
  )
}
