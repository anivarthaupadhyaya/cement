import { zodResolver } from '@hookform/resolvers/zod'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useForm } from 'react-hook-form'
import { z } from 'zod'

import { api } from '../api/client'
import type { Role, User } from '../api/types'
import { ROLE_LABELS } from '../api/types'
import { Badge, Button, Card, ErrorText, Field, Input, PageHeader, Select } from '../components/ui'
import { useMe } from '../lib/auth'

const schema = z.object({
  username: z.string().regex(/^[a-zA-Z0-9_.]{3,50}$/, '3–50 letters, digits, _ or .'),
  full_name: z.string().min(1, 'Required'),
  password: z.string().min(8, 'At least 8 characters'),
  role: z.enum(['owner', 'accountant', 'billing', 'godown']),
})
type Form = z.infer<typeof schema>

export function UsersPage() {
  const qc = useQueryClient()
  const { data: me } = useMe()
  const users = useQuery({ queryKey: ['users'], queryFn: () => api.get<User[]>('/api/users') })

  const { register, handleSubmit, reset, formState } = useForm<Form>({
    resolver: zodResolver(schema),
    defaultValues: { role: 'billing' },
  })
  const create = useMutation({
    mutationFn: (body: Form) => api.post<User>('/api/users', body),
    onSuccess: () => {
      reset({ username: '', full_name: '', password: '', role: 'billing' })
      qc.invalidateQueries({ queryKey: ['users'] })
    },
  })
  const toggle = useMutation({
    mutationFn: (u: User) => api.patch<User>(`/api/users/${u.id}`, { is_active: !u.is_active }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['users'] }),
  })

  return (
    <>
      <PageHeader title="Users" subtitle="Who can log in, and what they can do." />
      <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
        <Card>
          <ErrorText error={users.error ?? toggle.error} />
          <table className="w-full text-sm">
            <thead className="text-left text-stone-500">
              <tr>
                <th className="py-2">Name</th>
                <th>Username</th>
                <th>Role</th>
                <th>Status</th>
                <th />
              </tr>
            </thead>
            <tbody className="divide-y divide-stone-100">
              {users.data?.map((u) => (
                <tr key={u.id}>
                  <td className="py-2 font-medium">{u.full_name}</td>
                  <td className="text-stone-600">{u.username}</td>
                  <td>{ROLE_LABELS[u.role]}</td>
                  <td>{u.is_active ? <Badge tone="green">Active</Badge> : <Badge tone="red">Disabled</Badge>}</td>
                  <td className="text-right">
                    {u.id !== me?.id && (
                      <Button variant="ghost" onClick={() => toggle.mutate(u)} disabled={toggle.isPending}>
                        {u.is_active ? 'Disable' : 'Enable'}
                      </Button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>

        <Card title="Add user">
          <form onSubmit={handleSubmit((v) => create.mutate(v))} className="space-y-3">
            <Field label="Full name" error={formState.errors.full_name?.message}>
              <Input {...register('full_name')} />
            </Field>
            <Field label="Username" error={formState.errors.username?.message}>
              <Input autoComplete="off" {...register('username')} />
            </Field>
            <Field label="Password" error={formState.errors.password?.message}>
              <Input type="password" autoComplete="new-password" {...register('password')} />
            </Field>
            <Field label="Role">
              <Select {...register('role')}>
                {(Object.keys(ROLE_LABELS) as Role[]).map((r) => (
                  <option key={r} value={r}>
                    {ROLE_LABELS[r]}
                  </option>
                ))}
              </Select>
            </Field>
            <ErrorText error={create.error} />
            <Button type="submit" className="w-full" disabled={create.isPending}>
              Add user
            </Button>
          </form>
        </Card>
      </div>
    </>
  )
}
