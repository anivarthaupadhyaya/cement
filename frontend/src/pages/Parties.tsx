import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

import { api } from '../api/client'
import type { Party, PartyKind } from '../api/types'
import { Badge, Button, Card, ErrorText, Field, Input, PageHeader, Select } from '../components/ui'
import { useMe } from '../lib/auth'
import { formatINR } from '../lib/format'
import { can } from '../lib/roles'
import { STATES } from '../lib/states'
import { useDebounced } from '../lib/useDebounced'

type FormState = {
  kind: PartyKind
  name: string
  phone: string
  gstin: string
  state_code: string
  area: string
  address: string
  credit_limit: string
  credit_days: string
  notes: string
}

const EMPTY: FormState = {
  kind: 'customer',
  name: '',
  phone: '',
  gstin: '',
  state_code: '29',
  area: '',
  address: '',
  credit_limit: '0',
  credit_days: '0',
  notes: '',
}

const toForm = (p: Party): FormState => ({
  kind: p.kind,
  name: p.name,
  phone: p.phone ?? '',
  gstin: p.gstin ?? '',
  state_code: p.state_code,
  area: p.area ?? '',
  address: p.address ?? '',
  credit_limit: p.credit_limit,
  credit_days: String(p.credit_days),
  notes: p.notes ?? '',
})

const blankToNull = (v: string) => (v.trim() === '' ? null : v.trim())

export function PartiesPage() {
  const qc = useQueryClient()
  const { data: me } = useMe()
  const isOwner = can(me, 'owner')

  const [search, setSearch] = useState('')
  const [kind, setKind] = useState<'' | 'customer' | 'supplier'>('')
  const q = useDebounced(search)

  const parties = useQuery({
    queryKey: ['parties', q, kind],
    queryFn: () => {
      const params = new URLSearchParams()
      if (q) params.set('q', q)
      if (kind) params.set('kind', kind)
      return api.get<Party[]>(`/api/parties?${params}`)
    },
  })

  const [editing, setEditing] = useState<Party | null>(null)
  const [form, setForm] = useState<FormState>(EMPTY)
  const set = (k: keyof FormState) => (e: { target: { value: string } }) =>
    setForm((f) => ({ ...f, [k]: e.target.value }))

  const startNew = () => {
    setEditing(null)
    setForm(EMPTY)
  }
  const startEdit = (p: Party) => {
    setEditing(p)
    setForm(toForm(p))
  }

  const save = useMutation({
    mutationFn: () => {
      const body = {
        kind: form.kind,
        name: form.name.trim(),
        phone: blankToNull(form.phone),
        gstin: blankToNull(form.gstin),
        state_code: form.state_code,
        area: blankToNull(form.area),
        address: blankToNull(form.address),
        notes: blankToNull(form.notes),
        ...(isOwner ? { credit_limit: form.credit_limit || '0', credit_days: Number(form.credit_days || 0) } : {}),
      }
      return editing ? api.patch<Party>(`/api/parties/${editing.id}`, body) : api.post<Party>('/api/parties', body)
    },
    onSuccess: (p) => {
      qc.invalidateQueries({ queryKey: ['parties'] })
      setEditing(p)
      setForm(toForm(p))
    },
  })

  return (
    <>
      <PageHeader
        title="Customers & suppliers"
        subtitle="Contact details, GSTIN and credit terms."
        actions={<Button onClick={startNew}>New party</Button>}
      />
      <div className="grid gap-6 lg:grid-cols-[1fr_360px]">
        <Card>
          <div className="mb-3 flex flex-wrap gap-2">
            <Input
              className="max-w-xs"
              placeholder="Search name, phone or GSTIN"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
            <Select className="max-w-40" value={kind} onChange={(e) => setKind(e.target.value as typeof kind)}>
              <option value="">All</option>
              <option value="customer">Customers</option>
              <option value="supplier">Suppliers</option>
            </Select>
          </div>
          <ErrorText error={parties.error} />
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-left text-stone-500">
                <tr>
                  <th className="py-2">Name</th>
                  <th>Phone</th>
                  <th>GSTIN</th>
                  <th>Area</th>
                  <th className="text-right">Credit limit</th>
                  <th className="text-right">Days</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-stone-100">
                {parties.data?.map((p) => (
                  <tr
                    key={p.id}
                    onClick={() => startEdit(p)}
                    className={`cursor-pointer hover:bg-stone-50 ${editing?.id === p.id ? 'bg-brand-50' : ''} ${p.is_active ? '' : 'text-stone-400'}`}
                  >
                    <td className="py-2">
                      <span className="font-medium">{p.name}</span>{' '}
                      {p.kind !== 'customer' && <Badge tone="stone">{p.kind === 'supplier' ? 'Supplier' : 'Both'}</Badge>}
                    </td>
                    <td className="tabular-nums">{p.phone ?? '—'}</td>
                    <td className="font-mono text-xs">{p.gstin ?? '—'}</td>
                    <td>{p.area ?? '—'}</td>
                    <td className="text-right tabular-nums">
                      {Number(p.credit_limit) > 0 ? formatINR(p.credit_limit) : <span className="text-stone-400">Cash</span>}
                    </td>
                    <td className="text-right tabular-nums">{p.credit_days || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {parties.data?.length === 0 && <p className="py-6 text-center text-sm text-stone-500">No parties found.</p>}
          </div>
        </Card>

        <Card title={editing ? `Edit: ${editing.name}` : 'New party'}>
          <form
            className="space-y-3"
            onSubmit={(e) => {
              e.preventDefault()
              save.mutate()
            }}
          >
            <div className="grid grid-cols-2 gap-3">
              <Field label="Type">
                <Select value={form.kind} onChange={set('kind')}>
                  <option value="customer">Customer</option>
                  <option value="supplier">Supplier</option>
                  <option value="both">Both</option>
                </Select>
              </Field>
              <Field label="Phone">
                <Input inputMode="tel" value={form.phone} onChange={set('phone')} />
              </Field>
            </div>
            <Field label="Name">
              <Input required value={form.name} onChange={set('name')} />
            </Field>
            <Field label="GSTIN (optional)">
              <Input
                className="font-mono uppercase"
                maxLength={15}
                value={form.gstin}
                onChange={set('gstin')}
                placeholder="29ABCDE1234F1Z5"
              />
            </Field>
            <Field label="State">
              <Select value={form.state_code} onChange={set('state_code')} disabled={form.gstin.trim().length === 15}>
                {Object.entries(STATES).map(([code, name]) => (
                  <option key={code} value={code}>
                    {code} · {name}
                  </option>
                ))}
              </Select>
            </Field>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Area / route">
                <Input value={form.area} onChange={set('area')} />
              </Field>
              <Field label="Address">
                <Input value={form.address} onChange={set('address')} />
              </Field>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Credit limit (₹)">
                <Input inputMode="decimal" value={form.credit_limit} onChange={set('credit_limit')} disabled={!isOwner} />
              </Field>
              <Field label="Credit days">
                <Input inputMode="numeric" value={form.credit_days} onChange={set('credit_days')} disabled={!isOwner} />
              </Field>
            </div>
            {!isOwner && <p className="text-xs text-stone-500">Only the owner can give credit.</p>}
            <Field label="Notes">
              <Input value={form.notes} onChange={set('notes')} />
            </Field>
            <ErrorText error={save.error} />
            <div className="flex gap-2">
              <Button type="submit" className="flex-1" disabled={save.isPending}>
                {editing ? 'Save changes' : 'Add party'}
              </Button>
              {editing && (
                <Button
                  type="button"
                  variant="secondary"
                  onClick={() =>
                    api
                      .patch<Party>(`/api/parties/${editing.id}`, { is_active: !editing.is_active })
                      .then((p) => {
                        setEditing(p)
                        qc.invalidateQueries({ queryKey: ['parties'] })
                      })
                  }
                >
                  {editing.is_active ? 'Deactivate' : 'Activate'}
                </Button>
              )}
            </div>
          </form>
        </Card>
      </div>
    </>
  )
}
