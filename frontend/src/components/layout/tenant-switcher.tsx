import { Building, ChevronsUpDown } from 'lucide-react'
import { useAuth } from '@/features/auth/use-auth'

export function TenantSwitcher() {
  const { user, currentTenant, selectTenant } = useAuth()
  const memberships = user?.memberships ?? []
  if (!currentTenant) return null

  if (memberships.length === 1) {
    return (
      <span className="flex items-center gap-2 text-sm font-medium">
        <Building className="text-muted-foreground size-4" />
        {currentTenant.tenant_name}
      </span>
    )
  }

  return (
    <label className="relative flex items-center gap-2 text-sm font-medium">
      <Building className="text-muted-foreground pointer-events-none absolute left-2.5 size-4" />
      <span className="sr-only">Empresa activa</span>
      <select
        value={currentTenant.tenant_id}
        onChange={(e) => selectTenant(e.target.value)}
        className="bg-card hover:bg-muted focus-visible:ring-primary/30 h-9 max-w-64 appearance-none truncate rounded-md border pr-8 pl-8 focus-visible:ring-2 focus-visible:outline-none"
      >
        {memberships.map((m) => (
          <option key={m.tenant_id} value={m.tenant_id}>
            {m.tenant_name}
          </option>
        ))}
      </select>
      <ChevronsUpDown className="text-muted-foreground pointer-events-none absolute right-2.5 size-3.5" />
    </label>
  )
}
