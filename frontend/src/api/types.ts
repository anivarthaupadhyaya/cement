export type Role = 'owner' | 'accountant' | 'billing' | 'godown'

export interface User {
  id: number
  username: string
  full_name: string
  role: Role
  is_active: boolean
}

export interface AuditEntry {
  id: number
  table_name: string
  record_id: string | null
  action: 'INSERT' | 'UPDATE' | 'DELETE'
  user_id: number | null
  old_data: Record<string, unknown> | null
  new_data: Record<string, unknown> | null
  changed_at: string
}

export const ROLE_LABELS: Record<Role, string> = {
  owner: 'Owner',
  accountant: 'Accountant',
  billing: 'Billing clerk',
  godown: 'Godown keeper',
}
