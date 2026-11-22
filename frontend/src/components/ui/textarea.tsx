import type { TextareaHTMLAttributes } from 'react'
import { cn } from '@/lib/utils'

export function Textarea({ className, ...props }: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      className={cn(
        'bg-card placeholder:text-muted-foreground focus-visible:border-primary focus-visible:ring-primary/30 min-h-20 w-full rounded-md border px-3 py-2 text-sm shadow-xs focus-visible:ring-2 focus-visible:outline-none',
        className,
      )}
      {...props}
    />
  )
}
