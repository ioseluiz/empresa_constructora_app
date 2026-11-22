import { Building2, ShieldCheck } from 'lucide-react'
import type { ReactNode } from 'react'

export function AuthLayout({
  title,
  subtitle,
  children,
}: {
  title: string
  subtitle?: string
  children: ReactNode
}) {
  return (
    <div className="grid min-h-screen lg:grid-cols-[1fr_1.1fr]">
      <aside className="bg-sidebar text-sidebar-foreground relative hidden flex-col justify-between overflow-hidden p-10 lg:flex">
        <div
          aria-hidden
          className="absolute inset-0 [background-image:linear-gradient(var(--sidebar-foreground)_1px,transparent_1px),linear-gradient(90deg,var(--sidebar-foreground)_1px,transparent_1px)] [background-size:48px_48px] opacity-[0.07]"
        />
        <div className="relative flex items-center gap-2.5">
          <span className="bg-accent text-sidebar flex size-9 items-center justify-center rounded-md">
            <Building2 className="size-5" />
          </span>
          <span className="text-lg font-semibold tracking-tight">Constructora</span>
        </div>
        <div className="relative max-w-md space-y-4">
          <h2 className="text-3xl leading-tight font-semibold tracking-tight">
            La planilla de todas tus obras, en un solo lugar.
          </h2>
          <p className="text-sidebar-muted">
            Marcaciones, planilla conforme a la ley panameña, vacaciones y comprobantes de pago para
            cada proyecto y la oficina central.
          </p>
        </div>
        <p className="text-sidebar-muted relative flex items-center gap-2 text-xs">
          <ShieldCheck className="size-4" /> Datos de cada empresa aislados y cifrados en tránsito.
        </p>
      </aside>

      <main className="flex items-center justify-center px-4 py-12 sm:px-8">
        <div className="w-full max-w-sm space-y-8">
          <div className="flex items-center gap-2.5 lg:hidden">
            <span className="bg-accent text-sidebar flex size-8 items-center justify-center rounded-md">
              <Building2 className="size-4.5" />
            </span>
            <span className="font-semibold tracking-tight">Constructora</span>
          </div>
          <div className="space-y-1.5">
            <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
            {subtitle && <p className="text-muted-foreground text-sm">{subtitle}</p>}
          </div>
          {children}
        </div>
      </main>
    </div>
  )
}
