import { errorCode } from '@/api/client'
import { useIamMeRetrieve } from '@/api/generated/iam/iam'
import { useAuth } from '@/features/auth/use-auth'

/** Permisos efectivos del usuario en la empresa activa. */
export function useAccess() {
  const { currentTenant } = useAuth()
  const query = useIamMeRetrieve({
    query: { enabled: !!currentTenant, retry: false, staleTime: 60_000 },
  })
  const permissions = new Set(query.data?.permissions ?? [])
  return {
    isLoading: query.isPending && !!currentTenant,
    mfaSetupRequired: errorCode(query.error) === 'mfa_setup_required',
    error: query.error,
    isOwner: query.data?.is_owner ?? false,
    roles: query.data?.roles ?? [],
    can: (permission: string) => permissions.has(permission),
  }
}
