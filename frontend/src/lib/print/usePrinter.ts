import { useState } from 'react'

import { bluetoothSupported, connectPrinter, print, printerName } from './bluetooth'

/** The page's Bluetooth printer: connect once (from a click), then print many times. */
export function usePrinter() {
  const [name, setName] = useState(printerName)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const run = async (work: () => Promise<unknown>) => {
    setBusy(true)
    setError(null)
    try {
      await work()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'print_failed')
    } finally {
      setBusy(false)
    }
  }
  return {
    supported: bluetoothSupported(),
    name,
    busy,
    error,
    connect: () => run(async () => setName(await connectPrinter())),
    print: (bytes: Uint8Array) => run(() => print(bytes)),
  }
}
