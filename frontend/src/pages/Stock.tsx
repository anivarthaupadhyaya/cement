import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

import { api } from '../api/client'
import type { Godown, Movement, StockRow } from '../api/types'
import { MOVEMENT_LABELS } from '../api/types'
import { Badge, Button, Card, ErrorText, Field, Input, PageHeader, Select } from '../components/ui'
import { useMe } from '../lib/auth'
import { formatDate, formatINR, paiseToRupees, toPaise } from '../lib/format'
import { can } from '../lib/roles'

function AdjustCard({ rows, godowns }: { rows: StockRow[]; godowns: Godown[] }) {
  const qc = useQueryClient()
  const products = Array.from(new Map(rows.map((r) => [r.product_id, r.product_name])).entries())
  const [form, setForm] = useState({ product_id: '', godown_id: '1', kind: 'damage', direction: 'out', qty: '', reason: '' })
  const set = (k: keyof typeof form) => (e: { target: { value: string } }) => setForm((f) => ({ ...f, [k]: e.target.value }))

  const save = useMutation({
    mutationFn: () => {
      const bags = Number(form.qty)
      const qty = form.kind === 'damage' || form.direction === 'out' ? -bags : bags
      return api.post<Movement>('/api/stock/adjustments', {
        product_id: Number(form.product_id),
        godown_id: Number(form.godown_id),
        kind: form.kind,
        qty,
        reason: form.reason.trim(),
      })
    },
    onSuccess: () => {
      setForm((f) => ({ ...f, qty: '', reason: '' }))
      qc.invalidateQueries({ queryKey: ['stock'] })
      qc.invalidateQueries({ queryKey: ['movements'] })
    },
  })

  return (
    <Card title="Record damage or correction">
      <form
        className="space-y-3"
        onSubmit={(e) => {
          e.preventDefault()
          save.mutate()
        }}
      >
        <Field label="Product">
          <Select required value={form.product_id} onChange={set('product_id')}>
            <option value="">Choose…</option>
            {products.map(([id, name]) => (
              <option key={id} value={id}>
                {name}
              </option>
            ))}
          </Select>
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Godown">
            <Select value={form.godown_id} onChange={set('godown_id')}>
              {godowns.map((g) => (
                <option key={g.id} value={g.id}>
                  {g.name}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Type">
            <Select value={form.kind} onChange={set('kind')}>
              <option value="damage">Damaged / burst bags</option>
              <option value="adjustment">Count correction</option>
            </Select>
          </Field>
        </div>
        <div className="grid grid-cols-2 gap-3">
          {form.kind === 'adjustment' && (
            <Field label="Direction">
              <Select value={form.direction} onChange={set('direction')}>
                <option value="out">Fewer bags than system</option>
                <option value="in">More bags than system</option>
              </Select>
            </Field>
          )}
          <Field label="Bags">
            <Input required inputMode="numeric" pattern="[1-9][0-9]*" value={form.qty} onChange={set('qty')} />
          </Field>
        </div>
        <Field label="Reason">
          <Input required minLength={3} value={form.reason} onChange={set('reason')} placeholder="e.g. 4 bags wet in rain" />
        </Field>
        <ErrorText error={save.error} />
        <Button type="submit" className="w-full" disabled={save.isPending}>
          Save
        </Button>
      </form>
    </Card>
  )
}

export function StockPage() {
  const { data: me } = useMe()
  const [godownId, setGodownId] = useState('')
  const [selected, setSelected] = useState<StockRow | null>(null)

  const godowns = useQuery({ queryKey: ['godowns'], queryFn: () => api.get<Godown[]>('/api/godowns') })
  const stock = useQuery({
    queryKey: ['stock', godownId],
    queryFn: () => api.get<StockRow[]>(`/api/stock${godownId ? `?godown_id=${godownId}` : ''}`),
  })
  const movements = useQuery({
    queryKey: ['movements', selected?.product_id, selected?.godown_id],
    queryFn: () =>
      api.get<Movement[]>(
        `/api/stock/movements?limit=50${selected ? `&product_id=${selected.product_id}&godown_id=${selected.godown_id}` : ''}`,
      ),
  })

  const showCost = stock.data?.some((r) => r.avg_cost !== null) ?? false
  const totalBags = stock.data?.reduce((a, r) => a + r.qty, 0) ?? 0
  const totalValue = stock.data?.reduce((a, r) => a + (r.value ? toPaise(r.value) : 0), 0) ?? 0
  const lowCount = stock.data?.filter((r) => r.low).length ?? 0
  const activeGodowns = godowns.data?.filter((g) => g.is_active) ?? []

  return (
    <>
      <PageHeader title="Stock" subtitle="Live bags in each godown. Click a row to see its history." />

      <div className="mb-6 grid gap-4 sm:grid-cols-3">
        <Card>
          <div className="text-sm text-stone-500">Bags in stock</div>
          <div className="text-2xl font-semibold tabular-nums">{totalBags.toLocaleString('en-IN')}</div>
        </Card>
        {showCost && (
          <Card>
            <div className="text-sm text-stone-500">Stock value (at cost)</div>
            <div className="text-2xl font-semibold tabular-nums">{formatINR(paiseToRupees(totalValue))}</div>
          </Card>
        )}
        <Card>
          <div className="text-sm text-stone-500">Low on stock</div>
          <div className={`text-2xl font-semibold tabular-nums ${lowCount ? 'text-red-600' : ''}`}>{lowCount}</div>
        </Card>
      </div>

      <div className="grid gap-6 lg:grid-cols-[1fr_340px]">
        <div className="space-y-6">
          <Card>
            {activeGodowns.length > 1 && (
              <Select className="mb-3 max-w-56" value={godownId} onChange={(e) => setGodownId(e.target.value)}>
                <option value="">All godowns</option>
                {activeGodowns.map((g) => (
                  <option key={g.id} value={g.id}>
                    {g.name}
                  </option>
                ))}
              </Select>
            )}
            <ErrorText error={stock.error} />
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="text-left text-stone-500">
                  <tr>
                    <th className="py-2">Product</th>
                    {activeGodowns.length > 1 && <th>Godown</th>}
                    <th className="text-right">Bags</th>
                    <th className="text-right">Reorder at</th>
                    {showCost && <th className="text-right">Avg cost</th>}
                    {showCost && <th className="text-right">Value</th>}
                  </tr>
                </thead>
                <tbody className="divide-y divide-stone-100">
                  {stock.data?.map((r) => {
                    const isSel = selected?.product_id === r.product_id && selected?.godown_id === r.godown_id
                    return (
                      <tr
                        key={`${r.product_id}-${r.godown_id}`}
                        onClick={() => setSelected(isSel ? null : r)}
                        className={`cursor-pointer hover:bg-stone-50 ${isSel ? 'bg-brand-50' : ''}`}
                      >
                        <td className="py-2 font-medium">
                          {r.product_name} {r.low && <Badge tone="red">Low</Badge>}
                        </td>
                        {activeGodowns.length > 1 && <td>{r.godown_name}</td>}
                        <td className="text-right text-base font-semibold tabular-nums">{r.qty}</td>
                        <td className="text-right text-stone-500 tabular-nums">{r.reorder_level}</td>
                        {showCost && <td className="text-right tabular-nums">{formatINR(r.avg_cost)}</td>}
                        {showCost && <td className="text-right tabular-nums">{formatINR(r.value)}</td>}
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </Card>

          <Card title={selected ? `History: ${selected.product_name}` : 'Recent stock movements'}>
            <ErrorText error={movements.error} />
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="text-left text-stone-500">
                  <tr>
                    <th className="py-2">Date</th>
                    {!selected && <th>Product</th>}
                    <th>What</th>
                    <th className="text-right">Bags</th>
                    {showCost && <th className="text-right">Cost / bag</th>}
                    <th>Note</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-stone-100">
                  {movements.data?.map((m) => (
                    <tr key={m.id}>
                      <td className="py-2 whitespace-nowrap text-stone-600">{formatDate(m.movement_date)}</td>
                      {!selected && <td>{m.product_name}</td>}
                      <td>{MOVEMENT_LABELS[m.kind] ?? m.kind}</td>
                      <td className={`text-right font-medium tabular-nums ${m.qty < 0 ? 'text-red-600' : 'text-green-700'}`}>
                        {m.qty > 0 ? `+${m.qty}` : m.qty}
                      </td>
                      {showCost && <td className="text-right tabular-nums">{formatINR(m.unit_cost)}</td>}
                      <td className="text-stone-500">{m.note ?? ''}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {movements.data?.length === 0 && <p className="py-4 text-center text-sm text-stone-500">No movements yet.</p>}
            </div>
          </Card>
        </div>

        {can(me, 'owner', 'accountant', 'godown') && stock.data && (
          <div>
            <AdjustCard rows={stock.data} godowns={activeGodowns} />
          </div>
        )}
      </div>
    </>
  )
}
