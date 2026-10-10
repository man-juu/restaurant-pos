import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { CheckInput } from '../../components/form'
import { Button } from '../../components/ui'
import type { TicketOut } from '../../lib/api/types'
import { ticketBytes } from '../../lib/print/layouts'
import { usePrinter } from '../../lib/print/usePrinter'

const AUTO_KEY = 'kitchen.autoPrint'

function readAuto(): boolean {
  try {
    return localStorage.getItem(AUTO_KEY) === '1'
  } catch {
    return false
  }
}

/** FR-KDS-002: this station's printer; new tickets print by themselves when switched on
 * (a per-device choice, kept in this browser only). */
export function KitchenPrinter({ tickets }: { tickets: TicketOut[] }) {
  const { t } = useTranslation()
  const printer = usePrinter()
  const [auto, setAuto] = useState(readAuto)
  const seen = useRef<Set<string> | null>(null)
  useEffect(() => {
    const fresh = tickets.filter((k) => k.status === 'new' && !seen.current?.has(k.id))
    // The first load only remembers what is already there: no reprinting old tickets.
    if (seen.current !== null && auto && printer.name)
      for (const k of fresh) void printer.print(ticketBytes(k, t))
    seen.current = new Set([...(seen.current ?? []), ...tickets.map((k) => k.id)])
  }, [tickets, auto, printer, t])
  const toggle = (on: boolean) => {
    setAuto(on)
    try {
      localStorage.setItem(AUTO_KEY, on ? '1' : '0')
    } catch {
      // storage blocked: the choice lasts until the page closes
    }
  }
  if (!printer.supported) return null
  return (
    <div className="flex flex-wrap items-end gap-3">
      {printer.name ? (
        <span className="text-sm">{t('receipt.connected', { printer: printer.name })}</span>
      ) : (
        <Button variant="ghost" onClick={() => void printer.connect()}>
          {t('receipt.connect')}
        </Button>
      )}
      <CheckInput label={t('kitchen.autoPrint')} checked={auto} onChange={toggle} />
    </div>
  )
}
