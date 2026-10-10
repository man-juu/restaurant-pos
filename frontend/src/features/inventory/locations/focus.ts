/** A scanned item jumps to its line: scroll the input with this id into view and focus it. */
export const focusLine = (id: string) => {
  const input = document.getElementById(id)
  input?.scrollIntoView({ block: 'center' })
  input?.focus()
}
