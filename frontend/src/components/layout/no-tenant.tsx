import { Building2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useAuth } from '@/features/auth/use-auth'

export function NoTenant() {
  const { user, logout } = useAuth()
  return (
    <div className="flex min-h-screen items-center justify-center px-4">
      <div className="max-w-sm space-y-4 text-center">
        <span className="bg-muted mx-auto flex size-12 items-center justify-center rounded-full">
          <Building2 className="text-muted-foreground size-6" />
        </span>
        <h1 className="text-lg font-semibold">Sin empresa asignada</h1>
        <p className="text-muted-foreground text-sm">
          La cuenta <strong>{user?.email}</strong> todavía no tiene acceso a ninguna empresa. Pide
          al administrador de tu empresa que te agregue.
        </p>
        <Button variant="outline" onClick={() => void logout()}>
          Cerrar sesión
        </Button>
      </div>
    </div>
  )
}
