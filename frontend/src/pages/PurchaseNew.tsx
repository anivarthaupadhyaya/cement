import { useMutation, useQuery } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { api } from '../api/client'
import type { Godown, Party, Product, Purchase } from '../api/types'
import { Button, Card, ErrorText, Field, Input, PageHeader, Select } from '../components/ui'
import { formatINR, paiseToRupees, todayISO, toPaise } from '../lib/format'

interface Line {
  key: number
  product_id: string
  qty_invoiced: string
  qty_damaged: string
  qty_short: string
  rate: string
}

let nextKey = 1
const blankLine = (): Line => ({
  key: nextKey++,
  product_id: '',
  qty_invoiced: '',
  qty_damaged: '0',
  qty_short: '0',
  rate: '',
})

const int = (v: string) => (/^\d+$/.test(v.trim()) ? Number(v) : NaN)

export function PurchaseNewPage() {
  const navigate = useNavigate()
  const suppliers = useQuery({
    queryKey: ['parties', 'suppliers'],
    queryFn: () => api.get<Party[]>('/api/parties?kind=supplier&active=true&limit=1000'),
  })
  const products = useQuery({
    queryKey: ['products', 'active'],
    queryFn: () => api.get<Product[]>('/api/products?active=true'),
  })
  const godowns = useQuery({ queryKey: ['godowns'], queryFn: () => api.get<Godown[]>('/api/godowns') })

  const [head, setHead] = useState({
    supplier_id: '',
    supplier_invoice_no: '',
    invoice_date: todayISO(),
    received_date: todayISO(),
    godown_id: '1',
    vehicle_no: '',
    lr_no: '',
    freight: '0',
    unloading: '0',
    other_charges: '0',
    notes: '',
  })
  const [lines, setLines] = useState<Line[]>([blankLine()])
  const setH = (k: keyof typeof head) => (e: { target: { value: string } }) =>
    setHead((h) => ({ ...h, [k]: e.target.value }))
  const setL = (key: number, k: keyof Line, v: string) =>
    setLines((ls) => ls.map((l) => (l.key === key ? { ...l, [k]: v } : l)))

  // Display-only estimate in integer paise; the server does the real maths.
  const estimate = useMemo(() => {
    let taxable = 0
    let bags = 0
    for (const l of lines) {
      const q = int(l.qty_invoiced)
      const r = toPaise(l.rate)
      if (!Number.isNaN(q) && !Number.isNaN(r)) {
        taxable += q * r
        bags += q
      }
    }
    const charges = ['freight', 'unloading', 'other_charges']
      .map((k) => toPaise(head[k as 'freight']))
      .reduce((a, b) => a + (Number.isNaN(b) ? 0 : b), 0)
    return { taxable, bags, charges }
  }, [lines, head])

  const lineErrors = lines.map((l) => {
    if (!l.product_id) return 'Choose a product'
    const billed = int(l.qty_invoiced)
    const damaged = int(l.qty_damaged || '0')
    const short = int(l.qty_short || '0')
    if (!(billed > 0)) return 'Bags billed?'
    if (Number.isNaN(damaged) || Number.isNaN(short)) return 'Whole bags only'
    if (damaged + short > billed) return 'Damaged + short is more than billed'
    if (!(toPaise(l.rate) > 0)) return 'Rate?'
    return null
  })
  const duplicate = new Set(lines.map((l) => l.product_id)).size !== lines.length
  const canSave = head.supplier_id && head.supplier_invoice_no.trim() && lineErrors.every((e) => !e) && !duplicate

  const save = useMutation({
    mutationFn: () =>
      api.post<Purchase>('/api/purchases', {
        supplier_id: Number(head.supplier_id),
        supplier_invoice_no: head.supplier_invoice_no.trim(),
        invoice_date: head.invoice_date,
        received_date: head.received_date,
        godown_id: Number(head.godown_id),
        vehicle_no: head.vehicle_no.trim().toUpperCase() || null,
        lr_no: head.lr_no.trim() || null,
        freight: head.freight || '0',
        unloading: head.unloading || '0',
        other_charges: head.other_charges || '0',
        notes: head.notes.trim() || null,
        lines: lines.map((l) => {
          const billed = int(l.qty_invoiced)
          const damaged = int(l.qty_damaged || '0')
          const short = int(l.qty_short || '0')
          return {
            product_id: Number(l.product_id),
            qty_invoiced: billed,
            qty_damaged: damaged,
            qty_received: billed - damaged - short,
            rate: l.rate.trim(),
          }
        }),
      }),
    onSuccess: (p) => navigate(`/purchases/${p.id}`, { replace: true }),
  })

  return (
    <>
      <PageHeader title="New purchase" subtitle="Enter the supplier's bill as printed. Rates are per bag, before GST." />
      <form
        className="space-y-6"
        onSubmit={(e) => {
          e.preventDefault()
          if (canSave) save.mutate()
        }}
      >
        <Card title="Bill details">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Field label="Supplier">
              <Select required value={head.supplier_id} onChange={setH('supplier_id')} autoFocus>
                <option value="">Choose…</option>
                {suppliers.data?.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Supplier bill no.">
              <Input required value={head.supplier_invoice_no} onChange={setH('supplier_invoice_no')} />
            </Field>
            <Field label="Bill date">
              <Input type="date" max={todayISO()} required value={head.invoice_date} onChange={setH('invoice_date')} />
            </Field>
            <Field label="Received on">
              <Input type="date" required value={head.received_date} onChange={setH('received_date')} />
            </Field>
            <Field label="Into godown">
              <Select value={head.godown_id} onChange={setH('godown_id')}>
                {godowns.data
                  ?.filter((g) => g.is_active)
                  .map((g) => (
                    <option key={g.id} value={g.id}>
                      {g.name}
                    </option>
                  ))}
              </Select>
            </Field>
            <Field label="Truck no.">
              <Input className="uppercase" value={head.vehicle_no} onChange={setH('vehicle_no')} placeholder="KA20AB1234" />
            </Field>
            <Field label="LR no.">
              <Input value={head.lr_no} onChange={setH('lr_no')} />
            </Field>
          </div>
          {suppliers.data?.length === 0 && (
            <p className="mt-3 text-sm text-amber-700">
              No suppliers yet. Add one under Customers &amp; suppliers with type “Supplier”.
            </p>
          )}
        </Card>

        <Card title="Bags">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-left text-stone-500">
                <tr>
                  <th className="py-2">Product</th>
                  <th className="w-28 text-right">Billed</th>
                  <th className="w-28 text-right">Damaged</th>
                  <th className="w-28 text-right">Short</th>
                  <th className="w-28 text-right">Good</th>
                  <th className="w-36 text-right">Rate / bag</th>
                  <th className="w-32 text-right">Amount</th>
                  <th className="w-10" />
                </tr>
              </thead>
              <tbody className="divide-y divide-stone-100">
                {lines.map((l, i) => {
                  const billed = int(l.qty_invoiced)
                  const good = billed - int(l.qty_damaged || '0') - int(l.qty_short || '0')
                  const amount = billed * toPaise(l.rate)
                  return (
                    <tr key={l.key} className="align-top">
                      <td className="py-1.5 pr-2">
                        <Select value={l.product_id} onChange={(e) => setL(l.key, 'product_id', e.target.value)}>
                          <option value="">Choose…</option>
                          {products.data?.map((p) => (
                            <option key={p.id} value={p.id}>
                              {p.name}
                            </option>
                          ))}
                        </Select>
                        {lineErrors[i] && (l.product_id || l.qty_invoiced) && (
                          <span className="text-xs text-red-600">{lineErrors[i]}</span>
                        )}
                      </td>
                      {(['qty_invoiced', 'qty_damaged', 'qty_short'] as const).map((k) => (
                        <td key={k} className="py-1.5 pl-2">
                          <Input
                            className="text-right tabular-nums"
                            inputMode="numeric"
                            value={l[k]}
                            onChange={(e) => setL(l.key, k, e.target.value)}
                          />
                        </td>
                      ))}
                      <td className="py-3 text-right font-medium tabular-nums">{Number.isNaN(good) ? '—' : good}</td>
                      <td className="py-1.5 pl-2">
                        <Input
                          className="text-right tabular-nums"
                          inputMode="decimal"
                          value={l.rate}
                          onChange={(e) => setL(l.key, 'rate', e.target.value)}
                        />
                      </td>
                      <td className="py-3 text-right tabular-nums">
                        {Number.isNaN(amount) ? '—' : formatINR(paiseToRupees(amount))}
                      </td>
                      <td className="py-1.5 text-right">
                        {lines.length > 1 && (
                          <Button
                            type="button"
                            variant="ghost"
                            aria-label="Remove line"
                            onClick={() => setLines((ls) => ls.filter((x) => x.key !== l.key))}
                          >
                            ✕
                          </Button>
                        )}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
          {duplicate && <p className="mt-2 text-sm text-red-600">The same product is on two lines.</p>}
          <Button type="button" variant="secondary" className="mt-3" onClick={() => setLines((ls) => [...ls, blankLine()])}>
            + Add product
          </Button>
        </Card>

        <div className="grid gap-6 lg:grid-cols-2">
          <Card title="Charges paid by us">
            <p className="mb-3 text-sm text-stone-500">Spread over the bags by weight to get the real cost per bag.</p>
            <div className="grid grid-cols-3 gap-3">
              <Field label="Freight">
                <Input inputMode="decimal" value={head.freight} onChange={setH('freight')} />
              </Field>
              <Field label="Unloading">
                <Input inputMode="decimal" value={head.unloading} onChange={setH('unloading')} />
              </Field>
              <Field label="Other">
                <Input inputMode="decimal" value={head.other_charges} onChange={setH('other_charges')} />
              </Field>
            </div>
            <div className="mt-3">
              <Field label="Notes">
                <Input value={head.notes} onChange={setH('notes')} />
              </Field>
            </div>
          </Card>

          <Card title="Summary">
            <dl className="space-y-1.5 text-sm">
              <div className="flex justify-between">
                <dt className="text-stone-500">Bags billed</dt>
                <dd className="tabular-nums">{estimate.bags}</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-stone-500">Taxable value</dt>
                <dd className="tabular-nums">{formatINR(paiseToRupees(estimate.taxable))}</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-stone-500">Our charges</dt>
                <dd className="tabular-nums">{formatINR(paiseToRupees(estimate.charges))}</dd>
              </div>
              <p className="pt-2 text-xs text-stone-500">
                GST, round-off and the cost per bag are worked out exactly when you save.
              </p>
            </dl>
            <ErrorText error={save.error} />
            <Button type="submit" className="mt-4 w-full" disabled={!canSave || save.isPending}>
              {save.isPending ? 'Saving…' : 'Save purchase & add to stock'}
            </Button>
          </Card>
        </div>
      </form>
    </>
  )
}
