import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { TextInput } from '../../../components/form'
import { Alert, Button } from '../../../components/ui'
import type { ScanOut } from '../../../lib/api/types'
import { errorMessage } from '../../../lib/errors'
import { hasCamera } from './camera'
import { CameraScan } from './CameraScan'
import { scanCode } from './locationApi'

/** FR-INV-019: type or scan a code (USB scanners type and press Enter; phones may use the
 * camera where the browser can read barcodes). */
export function ScanBox({
  outletId,
  onFound,
}: {
  outletId: string
  onFound: (hit: ScanOut) => void
}) {
  const { t, i18n } = useTranslation()
  const [code, setCode] = useState('')
  const [error, setError] = useState<unknown>(null)
  const [camera, setCamera] = useState(false)
  const look = (value: string) => {
    if (!value.trim()) return
    scanCode(outletId, value.trim(), i18n.language).then(
      (hit) => {
        setError(null)
        setCode('')
        onFound(hit)
      },
      (e: unknown) => setError(e),
    )
  }
  return (
    <div className="flex flex-col gap-2">
      <form
        className="flex flex-wrap items-end gap-2"
        onSubmit={(e) => {
          e.preventDefault()
          look(code)
        }}
      >
        <TextInput
          label={t('scan.code')}
          value={code}
          maxLength={80}
          autoComplete="off"
          onChange={(e) => setCode(e.target.value)}
        />
        <Button type="submit" variant="ghost">
          {t('scan.find')}
        </Button>
        {hasCamera() && (
          <Button type="button" variant="ghost" onClick={() => setCamera(!camera)}>
            {t(camera ? 'scan.stop' : 'scan.camera')}
          </Button>
        )}
      </form>
      {camera && (
        <CameraScan
          onCode={(c) => {
            setCamera(false)
            look(c)
          }}
        />
      )}
      {error ? <Alert>{errorMessage(error, t)}</Alert> : null}
    </div>
  )
}
