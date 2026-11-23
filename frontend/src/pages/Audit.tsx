import { useQuery } from '@tanstack/react-query'
import { Fragment, useState } from 'react'

import { api } from '../api/client'
import type { AuditEntry, User } from '../api/types'
import { Badge, Card, ErrorText, PageHeader } from '../components/ui'

const ACTION_TONE = { INSERT: 'green', UPDATE: 'amber', DELETE: 'red' } as const

function changedFields(e: AuditEntry): string[] {
  if (!e.old_data || !e.new_data) return []
  return Object.keys(e.new_data).filter(
    (k) => k !== 'updated_at' && JSON.stringify(e.old_data?.[k]) !== JSON.stringify(e.new_data?.[k]),
  )
}

export function AuditPage() {
  const [open, setOpen] = useState<number | null>(null)
  const audit = useQuery({ queryKey: ['audit'], queryFn: () => api.get<AuditEntry[]>('/api/audit?limit=200') })
  const users = useQuery({ queryKey: ['users'], queryFn: () => api.get<User[]>('/api/users') })
  const nameOf = (id: number | null) =>
    users.data?.find((u) => u.id === id)?.full_name ?? (id ? `#${id}` : 'System')

  return (
    <>
      <PageHeader
        title="Audit log"
        subtitle="Every change, who made it and when. Entries can't be edited or deleted."
      />
      <Card>
        <ErrorText error={audit.error} />
        <table className="w-full text-sm">
          <thead className="text-left text-stone-500">
            <tr>
              <th className="py-2">When</th>
              <th>Who</th>
              <th>Action</th>
              <th>Record</th>
              <th>Changed</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-stone-100">
            {audit.data?.map((e) => (
              <Fragment key={e.id}>
                <tr className="cursor-pointer hover:bg-stone-50" onClick={() => setOpen(open === e.id ? null : e.id)}>
                  <td className="py-2 whitespace-nowrap text-stone-600">
                    {new Date(e.changed_at).toLocaleString('en-IN')}
                  </td>
                  <td>{nameOf(e.user_id)}</td>
                  <td>
                    <Badge tone={ACTION_TONE[e.action]}>{e.action}</Badge>
                  </td>
                  <td>
                    {e.table_name} #{e.record_id}
                  </td>
                  <td className="text-stone-600">{changedFields(e).join(', ')}</td>
                </tr>
                {open === e.id && (
                  <tr>
                    <td colSpan={5} className="bg-stone-50 p-3">
                      <div className="grid gap-3 md:grid-cols-2">
                        <pre className="overflow-auto rounded bg-white p-2 text-xs">
                          {e.old_data ? JSON.stringify(e.old_data, null, 2) : '—'}
                        </pre>
                        <pre className="overflow-auto rounded bg-white p-2 text-xs">
                          {e.new_data ? JSON.stringify(e.new_data, null, 2) : '—'}
                        </pre>
                      </div>
                    </td>
                  </tr>
                )}
              </Fragment>
            ))}
          </tbody>
        </table>
      </Card>
    </>
  )
}
