import type { Role, User } from '../api/types'

export const can = (user: User | undefined, ...roles: Role[]) => !!user && roles.includes(user.role)
