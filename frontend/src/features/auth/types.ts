export interface Membership {
  tenant_id: string
  tenant_name: string
  tenant_slug: string
  is_owner: boolean
}

export interface User {
  id: string
  email: string
  first_name: string
  last_name: string
  full_name: string
  memberships: Membership[]
}

export interface LoginResponse {
  access: string
  user: User
}
