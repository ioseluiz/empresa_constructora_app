import { KeyRound, LogOut } from 'lucide-react'
import { Link } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { useAuth } from '@/features/auth/use-auth'

function initials(name: string) {
  return name
    .split(/[\s@]+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join('')
}

export function UserMenu() {
  const { user, logout } = useAuth()
  if (!user) return null
  return (
    <div className="flex items-center gap-3">
      <Link
        to="/cuenta/seguridad"
        className="hover:bg-muted flex items-center gap-3 rounded-md px-1.5 py-1"
        title="Seguridad de la cuenta"
      >
        <div className="hidden text-right sm:block">
          <p className="text-sm leading-tight font-medium">{user.full_name}</p>
          <p className="text-muted-foreground text-xs leading-tight">{user.email}</p>
        </div>
        <span
          aria-hidden
          className="bg-primary/15 text-primary relative flex size-9 items-center justify-center rounded-full text-xs font-semibold"
        >
          {initials(user.full_name)}
          {!user.mfa_enabled && (
            <KeyRound
              className="bg-accent text-sidebar absolute -right-1 -bottom-1 size-4 rounded-full p-0.5"
              aria-label="Verificación en dos pasos inactiva"
            />
          )}
        </span>
      </Link>
      <Button variant="ghost" size="icon" onClick={() => void logout()} aria-label="Cerrar sesión">
        <LogOut className="size-4" />
      </Button>
    </div>
  )
}
