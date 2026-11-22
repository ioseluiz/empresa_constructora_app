import type { InputHTMLAttributes } from 'react'
import { cn } from '@/lib/utils'

export function Checkbox({ className, ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      type="checkbox"
      className={cn('accent-primary size-4 shrink-0 rounded border', className)}
      {...props}
    />
  )
}

interface SwitchProps {
  checked: boolean
  onCheckedChange: (checked: boolean) => void
  id?: string
  disabled?: boolean
  'aria-label'?: string
}

export function Switch({ checked, onCheckedChange, ...props }: SwitchProps) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      onClick={() => onCheckedChange(!checked)}
      className={cn(
        'focus-visible:ring-primary/40 relative inline-flex h-5 w-9 shrink-0 items-center rounded-full transition-colors focus-visible:ring-2 focus-visible:outline-none disabled:opacity-50',
        checked ? 'bg-primary' : 'bg-border',
      )}
      {...props}
    >
      <span
        className={cn(
          'inline-block size-4 rounded-full bg-white shadow transition-transform',
          checked ? 'translate-x-4.5' : 'translate-x-0.5',
        )}
      />
    </button>
  )
}
