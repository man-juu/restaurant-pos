// Performance budget for what a browser downloads first (NFR-001/NFR-002: slow mobile links).
// Fails the build if the gzipped entry JavaScript or CSS grows past the budget.
import { readdirSync, readFileSync } from 'node:fs'
import { join } from 'node:path'
import { gzipSync } from 'node:zlib'

const BUDGET = { js: 160 * 1024, css: 12 * 1024, anyChunk: 120 * 1024 }
const dir = 'dist/assets'
const html = readFileSync('dist/index.html', 'utf8')
let failed = false
const size = (file) => gzipSync(readFileSync(join(dir, file))).length

for (const file of readdirSync(dir)) {
  const kb = (size(file) / 1024).toFixed(1)
  const entry = html.includes(file)
  const kind = file.endsWith('.css') ? 'css' : file.endsWith('.js') ? 'js' : null
  if (!kind) continue
  const limit = entry ? BUDGET[kind] : BUDGET.anyChunk
  const ok = size(file) <= limit
  failed ||= !ok
  console.log(
    `${ok ? 'ok  ' : 'FAIL'} ${entry ? 'entry' : 'chunk'} ${file} ${kb} KB gzip (limit ${limit / 1024} KB)`,
  )
}
if (failed) {
  console.error('Bundle budget exceeded: split code or remove weight before raising the budget.')
  process.exit(1)
}
