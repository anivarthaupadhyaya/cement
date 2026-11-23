import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

import { api } from '../api/client'
import type { Godown, GstRate } from '../api/types'
import { Badge, Button, Card, ErrorText, Field, Input, PageHeader } from '../components/ui'
import { useMe } from '../lib/auth'
import { formatDate, todayISO } from '../lib/format'
import { can } from '../lib/roles'

function GodownsCard({ canEdit }: { canEdit: boolean }) {
  const qc = useQueryClient()
  const godowns = useQuery({ queryKey: ['godowns'], queryFn: () => api.get<Godown[]>('/api/godowns') })
  const [name, setName] = useState('')
  const add = useMutation({
    mutationFn: () => api.post<Godown>('/api/godowns', { name }),
    onSuccess: () => {
      setName('')
      qc.invalidateQueries({ queryKey: ['godowns'] })
    },
  })

  return (
    <Card title="Godowns">
      <ul className="mb-3 divide-y divide-stone-100 text-sm">
        {godowns.data?.map((g) => (
          <li key={g.id} className="flex items-center justify-between py-2">
            <span className="font-medium">{g.name}</span>
            {!g.is_active && <Badge>Inactive</Badge>}
          </li>
        ))}
      </ul>
      {canEdit && (
        <form
          className="flex gap-2"
          onSubmit={(e) => {
            e.preventDefault()
            add.mutate()
          }}
        >
          <Input placeholder="New godown name" value={name} onChange={(e) => setName(e.target.value)} required />
          <Button type="submit" variant="secondary" disabled={add.isPending}>
            Add
          </Button>
        </form>
      )}
      <div className="mt-2">
        <ErrorText error={godowns.error ?? add.error} />
      </div>
    </Card>
  )
}

function GstCard({ canEdit }: { canEdit: boolean }) {
  const qc = useQueryClient()
  const rates = useQuery({ queryKey: ['gst-rates'], queryFn: () => api.get<GstRate[]>('/api/gst-rates') })
  const [form, setForm] = useState({ hsn_code: '2523', rate: '', effective_from: todayISO() })
  const add = useMutation({
    mutationFn: () => api.post<GstRate>('/api/gst-rates', form),
    onSuccess: () => {
      setForm((f) => ({ ...f, rate: '' }))
      qc.invalidateQueries({ queryKey: ['gst-rates'] })
      qc.invalidateQueries({ queryKey: ['rate-card'] })
    },
  })

  return (
    <Card title="GST rates">
      <p className="mb-3 text-sm text-stone-500">
        When the law changes, add the new rate from its start date. Bills before that date keep the old rate.
      </p>
      <table className="mb-4 w-full text-sm">
        <thead className="text-left text-stone-500">
          <tr>
            <th className="py-1">HSN</th>
            <th className="text-right">Rate</th>
            <th className="text-right">From</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-stone-100">
          {rates.data?.map((r) => (
            <tr key={r.id}>
              <td className="py-1.5">{r.hsn_code}</td>
              <td className="text-right font-medium tabular-nums">{Number(r.rate)}%</td>
              <td className="text-right text-stone-600">{formatDate(r.effective_from)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {canEdit && (
        <form
          className="grid grid-cols-[1fr_1fr_1.4fr_auto] items-end gap-2"
          onSubmit={(e) => {
            e.preventDefault()
            add.mutate()
          }}
        >
          <Field label="HSN">
            <Input value={form.hsn_code} onChange={(e) => setForm({ ...form, hsn_code: e.target.value })} required />
          </Field>
          <Field label="Rate %">
            <Input
              inputMode="decimal"
              value={form.rate}
              onChange={(e) => setForm({ ...form, rate: e.target.value })}
              required
            />
          </Field>
          <Field label="From">
            <Input
              type="date"
              value={form.effective_from}
              onChange={(e) => setForm({ ...form, effective_from: e.target.value })}
              required
            />
          </Field>
          <Button type="submit" variant="secondary" disabled={add.isPending}>
            Add
          </Button>
        </form>
      )}
      <div className="mt-2">
        <ErrorText error={rates.error ?? add.error} />
      </div>
    </Card>
  )
}

export function SettingsPage() {
  const { data: me } = useMe()
  const canEdit = can(me, 'owner', 'accountant')
  return (
    <>
      <PageHeader title="Settings" subtitle="Godowns and GST rates." />
      <div className="grid gap-6 lg:grid-cols-2">
        <GodownsCard canEdit={canEdit} />
        <GstCard canEdit={canEdit} />
      </div>
    </>
  )
}
