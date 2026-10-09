/**
 * Web Bluetooth printing (FR-SAL-010). Works in Chrome on Android, Windows, macOS and
 * ChromeOS over HTTPS; not in iOS Safari or Firefox (the screen says so). The paired
 * printer stays connected for the life of the page.
 */

// Services used by common 58/80 mm Bluetooth LE thermal printers.
const SERVICES = [
  '000018f0-0000-1000-8000-00805f9b34fb',
  'e7810a71-73ae-499d-8c15-faa9aef0c3f2',
  '49535343-fe7d-4ae5-8fa9-9fafd205e455',
]
const CHUNK = 180 // bytes per write: small enough for every printer we know

interface Characteristic {
  properties: { write: boolean; writeWithoutResponse: boolean }
  writeValueWithoutResponse?: (data: BufferSource) => Promise<void>
  writeValue: (data: BufferSource) => Promise<void>
}
interface Service {
  getCharacteristics: () => Promise<Characteristic[]>
}
interface Device {
  name?: string
  gatt?: {
    connected: boolean
    connect: () => Promise<{ getPrimaryServices: () => Promise<Service[]> }>
  }
}
interface BluetoothApi {
  requestDevice: (options: {
    acceptAllDevices: boolean
    optionalServices: string[]
  }) => Promise<Device>
}

let printer: { device: Device; out: Characteristic } | null = null

export const bluetoothSupported = (): boolean =>
  typeof navigator !== 'undefined' && 'bluetooth' in navigator

export const printerName = (): string | null => (printer ? (printer.device.name ?? '?') : null)

async function writable(device: Device): Promise<Characteristic> {
  const server = await device.gatt!.connect()
  for (const service of await server.getPrimaryServices()) {
    for (const c of await service.getCharacteristics()) {
      if (c.properties.write || c.properties.writeWithoutResponse) return c
    }
  }
  throw new Error('printer_not_writable')
}

/** Ask the user to pick a printer (must run from a click). */
export async function connectPrinter(): Promise<string> {
  const bt = (navigator as unknown as { bluetooth: BluetoothApi }).bluetooth
  const device = await bt.requestDevice({ acceptAllDevices: true, optionalServices: SERVICES })
  printer = { device, out: await writable(device) }
  return device.name ?? '?'
}

export async function print(data: Uint8Array): Promise<void> {
  if (!printer) throw new Error('printer_not_connected')
  if (!printer.device.gatt?.connected) printer.out = await writable(printer.device)
  const { out } = printer
  for (let i = 0; i < data.length; i += CHUNK) {
    const part = data.slice(i, i + CHUNK)
    if (out.properties.writeWithoutResponse && out.writeValueWithoutResponse)
      await out.writeValueWithoutResponse(part)
    else await out.writeValue(part)
  }
}
