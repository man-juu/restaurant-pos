import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Alert, Button, Card } from '../../components/ui'
import { errorMessage } from '../../lib/errors'
import { MAX_IMPORT_BYTES, templateUrl, useCheckImport, useCommitImport } from './importApi'
import { ImportHistory } from './ImportHistory'

const ACCEPT = '.csv,.xlsx'

/** FR-IMP-001: choose a file, see every problem row first, then import all rows or none. */
export function ImportPanel({ onClose }: { onClose: () => void }) {
  const { t } = useTranslation()
  const [file, setFile] = useState<File | null>(null)
  const check = useCheckImport()
  const commit = useCommitImport()
  const tooBig = Boolean(file && file.size > MAX_IMPORT_BYTES)
  const ready = check.data && check.data.errors.length === 0 && check.data.rows_ok > 0

  const choose = (next: File | undefined) => {
    setFile(next ?? null)
    commit.reset()
    if (next && next.size <= MAX_IMPORT_BYTES) check.mutate(next)
  }

  return (
    <Card className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="font-display text-lg font-bold">{t('catalog.import.title')}</h2>
        <Button variant="ghost" onClick={onClose}>
          {t('catalog.import.close')}
        </Button>
      </div>
      <p className="text-sm text-muted">{t('catalog.import.help')}</p>
      <div className="flex flex-wrap gap-3 text-sm font-semibold">
        <a className="text-accent underline" href={templateUrl('xlsx')}>
          {t('catalog.import.templateXlsx')}
        </a>
        <a className="text-accent underline" href={templateUrl('csv')}>
          {t('catalog.import.templateCsv')}
        </a>
      </div>
      <label className="flex flex-col gap-1 text-sm font-semibold text-ink-soft">
        {t('catalog.import.file')}
        <input type="file" accept={ACCEPT} onChange={(e) => choose(e.target.files?.[0])} />
      </label>
      {tooBig && <Alert>{t('catalog.import.tooBig')}</Alert>}
      {check.error ? <Alert>{errorMessage(check.error, t)}</Alert> : null}
      {commit.error ? <Alert>{errorMessage(commit.error, t)}</Alert> : null}
      {check.data && <CheckResult rowsOk={check.data.rows_ok} errors={check.data.errors} />}
      <CommitButton
        commit={commit}
        file={file}
        ready={Boolean(ready)}
        rows={check.data?.rows_ok ?? 0}
      />
      <ImportHistory />
    </Card>
  )
}

function CommitButton({
  commit,
  file,
  ready,
  rows,
}: {
  commit: ReturnType<typeof useCommitImport>
  file: File | null
  ready: boolean
  rows: number
}) {
  const { t } = useTranslation()
  if (commit.isSuccess)
    return (
      <p className="font-semibold text-good">
        {t('catalog.import.done', { count: commit.data.row_count })}
      </p>
    )
  return (
    <Button
      onClick={() => file && commit.mutate(file)}
      disabled={!ready || commit.isPending}
      aria-busy={commit.isPending}
    >
      {t('catalog.import.confirm', { count: rows })}
    </Button>
  )
}

type RowError = { row?: number; field?: string }

function CheckResult({ rowsOk, errors }: { rowsOk: number; errors: RowError[] }) {
  const { t } = useTranslation()
  if (errors.length === 0)
    return <p className="text-sm text-good">{t('catalog.import.allGood', { count: rowsOk })}</p>
  return (
    <div className="flex flex-col gap-2">
      <p className="text-sm font-semibold text-warn">
        {t('catalog.import.problems', { count: errors.length })}
      </p>
      <ul className="max-h-48 overflow-y-auto rounded-lg border border-line text-sm">
        {errors.map((e, i) => (
          <li key={i} className="border-b border-line px-3 py-2 last:border-0">
            {t('catalog.import.rowProblem', {
              row: e.row,
              field: t(`catalog.import.fields.${e.field}`, { defaultValue: e.field }),
            })}
          </li>
        ))}
      </ul>
    </div>
  )
}
