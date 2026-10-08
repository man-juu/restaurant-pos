import { clsx } from 'clsx'
import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode } from 'react'

export function Button({
  variant = 'primary',
  className,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: 'primary' | 'ghost' }) {
  return (
    <button
      {...props}
      className={clsx(
        'inline-flex min-h-11 items-center justify-center gap-2 rounded-xl px-4 font-display text-sm font-extrabold transition disabled:opacity-50',
        variant === 'primary'
          ? 'bg-accent text-on-accent hover:bg-accent-soft'
          : 'border border-line-strong bg-card text-ink hover:bg-raised',
        className,
      )}
    />
  )
}

export function Field({
  label,
  trailing,
  ...props
}: InputHTMLAttributes<HTMLInputElement> & { label: string; trailing?: ReactNode }) {
  return (
    <label className="flex flex-col gap-2 text-sm font-semibold text-ink-soft">
      {label}
      <span className="relative flex">
        <input
          {...props}
          className="min-h-12 w-full rounded-xl border border-line-strong bg-ground px-3.5 text-base font-medium text-ink"
        />
        {trailing && (
          <span className="absolute inset-y-0 right-1 flex items-center">{trailing}</span>
        )}
      </span>
    </label>
  )
}

export function Card({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <section className={clsx('rounded-2xl border border-line bg-card p-5', className)}>
      {children}
    </section>
  )
}

export function Alert({ children }: { children: ReactNode }) {
  return (
    <p
      role="alert"
      className="rounded-xl border border-alert/40 bg-alert-surface px-4 py-3 text-sm text-ink"
    >
      {children}
    </p>
  )
}

const STATE_STYLES: Record<string, string> = {
  active: 'bg-good-surface text-good',
  free: 'bg-good-surface text-good',
  expiring: 'bg-warn-surface text-warn',
  grace: 'bg-alert-surface text-alert',
  read_only: 'bg-raised text-ink-soft',
  suspended: 'bg-danger-surface text-danger',
  posted: 'bg-good-surface text-good',
  reversed: 'bg-raised text-ink-soft',
}

export function StateBadge({ state, label }: { state: string; label: string }) {
  return (
    <span
      className={clsx(
        'rounded-full px-2.5 py-1 text-xs font-extrabold uppercase',
        STATE_STYLES[state] ?? 'bg-raised text-ink-soft',
      )}
    >
      {label}
    </span>
  )
}

export function Logo({ color = 'bg-accent' }: { color?: string }) {
  return (
    <span
      className={clsx(
        'flex h-9 w-9 items-center justify-center rounded-[10px] text-on-accent',
        color,
      )}
    >
      <svg
        width="20"
        height="20"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2.2"
        aria-hidden="true"
      >
        <path d="M3 11h18" />
        <path d="M5 11a7 7 0 0 1 14 0" />
        <path d="M4 15h16l-1 4H5z" />
      </svg>
    </span>
  )
}
