import { api } from '@/api/client'
import type { LoginResponse, User } from './types'

export const authApi = {
  login: (email: string, password: string) =>
    api.post<LoginResponse>('/auth/login/', { email, password }, { anonymous: true }),
  logout: () => api.post<void>('/auth/logout/', undefined, { anonymous: true }),
  me: () => api.get<User>('/auth/me/'),
  requestPasswordReset: (email: string) =>
    api.post<void>('/auth/password/reset/', { email }, { anonymous: true }),
  confirmPasswordReset: (uid: string, token: string, newPassword: string) =>
    api.post<void>(
      '/auth/password/reset/confirm/',
      { uid, token, new_password: newPassword },
      { anonymous: true },
    ),
}
