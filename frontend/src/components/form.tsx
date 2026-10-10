import { clsx } from 'clsx'
import type { InputHTMLAttributes, ReactNode, SelectHTMLAttributes } from 'react'

export const inputClass =
  'min-h-11 w-full rounded-lg border border-line-strong bg-ground px-3 text-ink'

const labelClass = 'flex flex-col gap-1 text-sm font-semibold text-ink-soft'

/** Labelled text input; `invalid` marks it for screen readers and in colour. */
export function TextInput({
  label,
  invalid,
  className,
  ...props
}: InputHTMLAttributes<HTMLInputElement> & { label: string; invalid?: boolean }) {
  return (
    <label className={clsx(labelClass, className)}>
      {label}
      <input
        {...props}
        aria-invalid={invalid || undefined}
        className={clsx(inputClass, invalid && 'border-danger')}
      />
    </label>
  )
}

export function SelectInput({
  label,
  children,
  className,
  ...props
}: SelectHTMLAttributes<HTMLSelectElement> & { label: string; children: ReactNode }) {
  return (
    <label className={clsx(labelClass, className)}>
      {label}
      <select {...props} className={inputClass}>
        {children}
      </select>
    </label>
  )
}

export function CheckInput({
  label,
  checked,
  onChange,
  disabled,
}: {
  label: string
  checked: boolean
  onChange: (value: boolean) => void
  disabled?: boolean
}) {
  return (
    <label className="flex min-h-11 items-center gap-2 text-sm">
      <input
        type="checkbox"
        className="h-5 w-5 accent-[var(--accent)]"
        checked={checked}
        disabled={disabled}
        onChange={(e) => onChange(e.target.checked)}
      />
      {label}
    </label>
  )
}

/** Tab strip used by multi-section pages. */
export function Tabs<T extends string>({
  tabs,
  value,
  onChange,
  label,
}: {
  tabs: readonly T[]
  value: T
  onChange: (tab: T) => void
  label: (tab: T) => string
}) {
  return (
    <div role="tablist" className="flex flex-wrap gap-2">
      {tabs.map((key) => (
        <button
          key={key}
          role="tab"
          type="button"
          aria-selected={value === key}
          onClick={() => onChange(key)}
          className={clsx(
            'min-h-11 rounded-xl border px-4 text-sm font-bold',
            value === key ? 'border-accent bg-raised text-ink' : 'border-line-strong text-ink-soft',
          )}
        >
          {label(key)}
        </button>
      ))}
    </div>
  )
}
