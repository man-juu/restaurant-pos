/** The browser's own barcode reader (Chrome on Android, among others); no extra library. */
export type Detector = { detect: (source: HTMLVideoElement) => Promise<{ rawValue: string }[]> }
export type DetectorClass = new (options: { formats: string[] }) => Detector
export const FORMATS = ['qr_code', 'code_128', 'ean_13', 'ean_8', 'upc_a', 'upc_e']

export const detectorClass = () =>
  (globalThis as unknown as { BarcodeDetector?: DetectorClass }).BarcodeDetector

export const hasCamera = () =>
  Boolean(detectorClass()) && Boolean(globalThis.navigator?.mediaDevices?.getUserMedia)
