import { ShieldOff } from 'lucide-react'
import type { ReactNode } from 'react'
import { EmptyState, LoadingBlock } from '@/components/ui/page'
import { useAccess } from './use-access'

export function RequirePermission({
  permission,
  children,
}: {
  permission: string
  children: ReactNode
}) {
  const { can, isLoading } = useAccess()
  if (isLoading) return <LoadingBlock />
  if (!can(permission)) {
    return (
      <EmptyState
        icon={ShieldOff}
        title="Sin acceso"
        description="Tu rol no incluye permiso para ver esta sección. Pide acceso al administrador de la empresa."
      />
    )
  }
  return <>{children}</>
}
