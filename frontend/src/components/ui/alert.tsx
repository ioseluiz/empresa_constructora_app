import { cva, type VariantProps } from 'class-variance-authority'
import type { HTMLAttributes } from 'react'
import { cn } from '@/lib/utils'

const alertVariants = cva('rounded-md border px-3.5 py-3 text-sm', {
  variants: {
    variant: {
      danger: 'border-danger/30 bg-danger/10 text-danger',
      success: 'border-success/30 bg-success/10 text-success',
    },
  },
  defaultVariants: { variant: 'danger' },
})

export function Alert({
  className,
  variant,
  ...props
}: HTMLAttributes<HTMLDivElement> & VariantProps<typeof alertVariants>) {
  return <div role="alert" className={cn(alertVariants({ variant }), className)} {...props} />
}
