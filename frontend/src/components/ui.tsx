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
          ? 'bg-accent text-ground hover:bg-accent-soft'
          : 'border border-line-strong bg-card text-ink hover:bg-raised',
        className,
      )}
    />
  )
}

export function Field({
  label,
  ...props
}: InputHTMLAttributes<HTMLInputElement> & { label: string }) {
  return (
    <label className="flex flex-col gap-2 text-sm font-semibold text-ink-soft">
      {label}
      <input
        {...props}
        className="min-h-12 rounded-xl border border-line-strong bg-ground px-3.5 text-base font-medium text-ink"
      />
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
    <p role="alert" className="rounded-xl border border-[#4a2e1d] bg-[#2a1a12] px-4 py-3 text-sm">
      {children}
    </p>
  )
}

const STATE_STYLES: Record<string, string> = {
  active: 'bg-[#16302a] text-[#7debc0]',
  free: 'bg-[#16302a] text-[#7debc0]',
  expiring: 'bg-[#3a3314] text-[#ffe27d]',
  grace: 'bg-[#3a1f14] text-[#ffb37d]',
  read_only: 'bg-[#2a2f3d] text-ink-soft',
  suspended: 'bg-[#3a1418] text-[#ff9aa6]',
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
    <span className={clsx('flex h-9 w-9 items-center justify-center rounded-[10px]', color)}>
      <svg
        width="20"
        height="20"
        viewBox="0 0 24 24"
        fill="none"
        stroke="#0B0E14"
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
