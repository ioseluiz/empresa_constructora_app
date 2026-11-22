import type { SelectHTMLAttributes } from 'react'
import { cn } from '@/lib/utils'

export function Select({ className, ...props }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      className={cn(
        'bg-card focus-visible:border-primary focus-visible:ring-primary/30 h-10 rounded-md border px-3 text-sm shadow-xs focus-visible:ring-2 focus-visible:outline-none',
        className,
      )}
      {...props}
    />
  )
}
