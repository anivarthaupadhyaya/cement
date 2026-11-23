import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { Navigate, useLocation } from 'react-router-dom'

import { api, ApiError } from '../api/client'
import type { Role, User } from '../api/types'

export function useMe() {
  return useQuery({
    queryKey: ['me'],
    queryFn: () => api.get<User>('/api/auth/me'),
    retry: (count, err) => !(err instanceof ApiError && err.status === 401) && count < 2,
    staleTime: 5 * 60_000,
  })
}

export function useLogout() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => api.post<void>('/api/auth/logout'),
    onSettled: () => qc.clear(),
  })
}

export function RequireAuth({ children, roles }: { children: ReactNode; roles?: Role[] }) {
  const { data: user, isLoading, error } = useMe()
  const location = useLocation()

  if (isLoading) return <div className="p-8 text-stone-500">Loading…</div>
  if (error || !user) return <Navigate to="/login" replace state={{ from: location }} />
  if (roles && !roles.includes(user.role)) {
    return <div className="p-8 text-stone-600">You don't have access to this page.</div>
  }
  return <>{children}</>
}
