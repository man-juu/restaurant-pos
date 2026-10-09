import * as Dialog from '@radix-ui/react-dialog'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { CheckInput, TextInput } from '../../components/form'
import { Button } from '../../components/ui'
import type { MenuItemOut } from '../../lib/api/types'
import { formatMoney, intlLocale } from '../../lib/format'
import { choiceValid, type Group } from './modifierChoice'

/** Pick an item's options (size, add-ons) and a kitchen note before it goes on the order. */
export function ModifierDialog({
  item,
  currency,
  onAdd,
  onClose,
}: {
  item: MenuItemOut
  currency: string
  onAdd: (optionIds: string[], note: string) => void
  onClose: () => void
}) {
  const { t, i18n } = useTranslation()
  const [picked, setPicked] = useState<string[]>([])
  const [note, setNote] = useState('')
  const money = (v: number) => formatMoney(v, currency, intlLocale(i18n.language))
  const toggle = (group: Group, id: string, on: boolean) => {
    const single = (group.max_select ?? 1) === 1
    const others = single ? picked.filter((p) => !group.options.some((o) => o.id === p)) : picked
    setPicked(on ? [...others, id] : picked.filter((p) => p !== id))
  }
  return (
    <Dialog.Root open onOpenChange={(open) => !open && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 bg-black/40" />
        <Dialog.Content className="fixed top-1/2 left-1/2 flex max-h-[90vh] w-[min(94vw,480px)] -translate-x-1/2 -translate-y-1/2 flex-col gap-4 overflow-y-auto rounded-2xl border border-line-strong bg-card p-5 text-ink shadow-2xl">
          <Dialog.Title className="font-display text-xl font-bold">{item.name}</Dialog.Title>
          <Dialog.Description className="text-sm text-ink-soft">
            {t('pos.chooseOptions')}
          </Dialog.Description>
          {item.modifier_groups.map((g) => (
            <fieldset key={g.id} className="flex flex-col gap-1">
              <legend className="font-bold">
                {g.name}{' '}
                <span className="text-sm font-normal text-ink-soft">
                  {t('pos.pickRange', { min: g.min_select ?? 0, max: g.max_select ?? 1 })}
                </span>
              </legend>
              {g.options.map((o) => (
                <CheckInput
                  key={o.id}
                  label={
                    o.price_delta
                      ? `${o.name} (${o.price_delta > 0 ? '+' : ''}${money(o.price_delta ?? 0)})`
                      : o.name
                  }
                  checked={picked.includes(o.id)}
                  onChange={(on) => toggle(g, o.id, on)}
                />
              ))}
            </fieldset>
          ))}
          <TextInput
            label={t('pos.note')}
            value={note}
            maxLength={200}
            onChange={(e) => setNote(e.target.value)}
          />
          <div className="flex flex-wrap gap-2">
            <Button
              disabled={!choiceValid(item.modifier_groups, picked)}
              onClick={() => onAdd(picked, note)}
            >
              {t('pos.addToOrder')}
            </Button>
            <Button variant="ghost" onClick={onClose}>
              {t('catalog.cancel')}
            </Button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
