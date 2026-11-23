import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link, useLocation, useParams } from 'react-router-dom'

import { api } from '../api/client'
import type { Sale } from '../api/types'
import { Badge, Button, Card, ErrorText, Field, Input, PageHeader } from '../components/ui'
import { useMe } from '../lib/auth'
import { formatDate, formatINR } from '../lib/format'
import { can } from '../lib/roles'

function ReturnCard({ sale, onDone }: { sale: Sale; onDone: (s: Sale) => void }) {
  const [qty, setQty] = useState<Record<number, string>>({})
  const [reason, setReason] = useState('')
  const items = Object.entries(qty)
    .filter(([, v]) => /^[1-9]\d*$/.test(v.trim()))
    .map(([id, v]) => ({ sales_line_id: Number(id), qty: Number(v) }))
  const save = useMutation({
    mutationFn: () => api.post<Sale>(`/api/sales/${sale.id}/returns`, { reason, items }),
    onSuccess: (s) => {
      setQty({})
      setReason('')
      onDone(s)
    },
  })
  const returnable = sale.lines.filter((l) => l.qty > l.qty_returned)
  if (returnable.length === 0) return null

  return (
    <Card title="Take back bags (credit note)">
      <form
        className="space-y-3"
        onSubmit={(e) => {
          e.preventDefault()
          save.mutate()
        }}
      >
        {returnable.map((l) => (
          <div key={l.id} className="flex items-center justify-between gap-3 text-sm">
            <span>
              {l.product_name} <span className="text-stone-500">(up to {l.qty - l.qty_returned})</span>
            </span>
            <Input
              className="w-20 text-right"
              inputMode="numeric"
              value={qty[l.id] ?? ''}
              onChange={(e) => setQty({ ...qty, [l.id]: e.target.value })}
            />
          </div>
        ))}
        <Field label="Reason">
          <Input required minLength={3} value={reason} onChange={(e) => setReason(e.target.value)} />
        </Field>
        <ErrorText error={save.error} />
        <Button type="submit" variant="secondary" className="w-full" disabled={items.length === 0 || save.isPending}>
          Issue credit note
        </Button>
      </form>
    </Card>
  )
}

export function SaleDetailPage() {
  const { id } = useParams()
  const location = useLocation()
  const justSaved = (location.state as { justSaved?: boolean } | null)?.justSaved
  const qc = useQueryClient()
  const { data: me } = useMe()
  const sale = useQuery({ queryKey: ['sale', id], queryFn: () => api.get<Sale>(`/api/sales/${id}`) })

  const [confirming, setConfirming] = useState(false)
  const [reason, setReason] = useState('')
  const refresh = (s: Sale) => {
    qc.setQueryData(['sale', id], s)
    qc.invalidateQueries({ queryKey: ['sales'] })
    qc.invalidateQueries({ queryKey: ['stock'] })
  }
  const cancel = useMutation({
    mutationFn: () => api.post<Sale>(`/api/sales/${id}/cancel`, { reason }),
    onSuccess: (s) => {
      refresh(s)
      setConfirming(false)
    },
  })

  if (sale.isLoading) return <p className="text-stone-500">Loading…</p>
  if (sale.error || !sale.data) return <ErrorText error={sale.error} />
  const s = sale.data
  const active = s.status === 'active'

  return (
    <>
      {justSaved && (
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-lg bg-green-50 px-4 py-3 text-green-800">
          <span>
            Bill <b>{s.invoice_no}</b> saved · {formatINR(s.grand_total)}
          </span>
          <Link to="/sales/new">
            <Button>Next bill</Button>
          </Link>
        </div>
      )}
      <PageHeader
        title={s.invoice_no}
        subtitle={`${formatDate(s.invoice_date)} · ${s.customer_name}`}
        actions={
          <div className="flex flex-wrap items-center gap-2">
            {!active && <Badge tone="red">Cancelled</Badge>}
            <a href={`/sales/${s.id}/print`} target="_blank" rel="noreferrer">
              <Button variant={justSaved ? 'primary' : 'secondary'}>Print bill</Button>
            </a>
            <a href={`/sales/${s.id}/print?type=challan`} target="_blank" rel="noreferrer">
              <Button variant="secondary">Delivery challan</Button>
            </a>
            <Link to="/sales">
              <Button variant="ghost">All bills</Button>
            </Link>
          </div>
        }
      />
      {!active && (
        <p className="mb-4 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">
          Cancelled: {s.cancel_reason}. The bags went back into stock.
        </p>
      )}

      <div className="grid gap-6 lg:grid-cols-[1fr_340px]">
        <div className="space-y-6">
          <Card>
            <div className="mb-4 grid gap-1 text-sm sm:grid-cols-2">
              <div>
                <span className="text-stone-500">Customer: </span>
                {s.customer_name} {s.customer_gstin && <span className="font-mono text-xs">({s.customer_gstin})</span>}
              </div>
              <div>
                <span className="text-stone-500">Type: </span>
                {s.payment_mode === 'credit' ? 'Credit' : 'Cash'}
                {s.is_interstate && ' · IGST'}
              </div>
              {s.vehicle_no && (
                <div>
                  <span className="text-stone-500">Vehicle: </span>
                  {s.vehicle_no}
                </div>
              )}
              {s.delivery_address && (
                <div>
                  <span className="text-stone-500">Deliver to: </span>
                  {s.delivery_address}
                </div>
              )}
              {s.credit_override_reason && (
                <div className="sm:col-span-2 text-amber-800">Over credit limit, approved: {s.credit_override_reason}</div>
              )}
            </div>
            <table className="w-full text-sm">
              <thead className="text-left text-stone-500">
                <tr>
                  <th className="py-2">Product</th>
                  <th className="text-right">Bags</th>
                  <th className="text-right">Rate</th>
                  <th className="text-right">Taxable</th>
                  <th className="text-right">GST</th>
                  {s.lines[0]?.cost_per_bag !== null && <th className="text-right">Cost/bag</th>}
                </tr>
              </thead>
              <tbody className="divide-y divide-stone-100">
                {s.lines.map((l) => (
                  <tr key={l.id}>
                    <td className="py-2 font-medium">
                      {l.product_name}
                      {l.qty_returned > 0 && <span className="ml-1 text-xs text-stone-500">({l.qty_returned} returned)</span>}
                    </td>
                    <td className="text-right tabular-nums">{l.qty}</td>
                    <td className="text-right tabular-nums">{formatINR(l.rate)}</td>
                    <td className="text-right tabular-nums">{formatINR(l.taxable)}</td>
                    <td className="text-right tabular-nums">{formatINR(l.gst_amount)}</td>
                    {l.cost_per_bag !== null && <td className="text-right tabular-nums text-stone-500">{formatINR(l.cost_per_bag)}</td>}
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>

          {s.returns.length > 0 && (
            <Card title="Credit notes">
              <ul className="divide-y divide-stone-100 text-sm">
                {s.returns.map((r) => (
                  <li key={r.id} className="flex justify-between py-2">
                    <span>
                      <span className="font-mono text-xs">{r.return_no}</span> · {formatDate(r.return_date)} ·{' '}
                      {r.lines.map((l) => `${l.qty} × ${l.product_name}`).join(', ')}
                      <span className="text-stone-500"> · {r.reason}</span>
                    </span>
                    <span className="font-medium tabular-nums">{formatINR(r.total)}</span>
                  </li>
                ))}
              </ul>
            </Card>
          )}
        </div>

        <div className="space-y-6">
          <Card title="Total">
            <dl className="space-y-1.5 text-sm">
              <div className="flex justify-between">
                <dt className="text-stone-500">Taxable</dt>
                <dd className="tabular-nums">{formatINR(s.taxable_total)}</dd>
              </div>
              {s.is_interstate ? (
                <div className="flex justify-between">
                  <dt className="text-stone-500">IGST</dt>
                  <dd className="tabular-nums">{formatINR(s.igst_total)}</dd>
                </div>
              ) : (
                <div className="flex justify-between">
                  <dt className="text-stone-500">CGST + SGST</dt>
                  <dd className="tabular-nums">
                    {formatINR(s.cgst_total)} + {formatINR(s.sgst_total)}
                  </dd>
                </div>
              )}
              <div className="flex justify-between">
                <dt className="text-stone-500">Round off</dt>
                <dd className="tabular-nums">{formatINR(s.round_off)}</dd>
              </div>
              <div className="flex justify-between border-t border-stone-200 pt-2 text-xl font-bold">
                <dt>Total</dt>
                <dd className="tabular-nums">{formatINR(s.grand_total)}</dd>
              </div>
              {s.margin !== null && (
                <div className="flex justify-between">
                  <dt className="text-stone-500">Margin</dt>
                  <dd className="font-medium text-green-700 tabular-nums">{formatINR(s.margin)}</dd>
                </div>
              )}
            </dl>
            <p className="mt-2 text-xs text-stone-500">{s.amount_in_words}</p>
            {active && s.payment_mode === 'credit' && (
              <div className="mt-3 space-y-1 border-t border-stone-200 pt-3 text-sm">
                <div className="flex justify-between">
                  <span className="text-stone-500">Paid</span>
                  <span className="tabular-nums text-green-700">{formatINR(s.paid)}</span>
                </div>
                <div className="flex justify-between font-semibold">
                  <span>Balance due</span>
                  <span className={`tabular-nums ${Number(s.balance_due) > 0 ? 'text-red-700' : ''}`}>{formatINR(s.balance_due)}</span>
                </div>
                {s.party_id && (
                  <div className="flex gap-2 pt-2">
                    {Number(s.balance_due) > 0 && (
                      <Link to={`/receipts/new?party=${s.party_id}`} className="flex-1">
                        <Button className="w-full">Receive payment</Button>
                      </Link>
                    )}
                    <Link to={`/parties/${s.party_id}/ledger`} className="flex-1">
                      <Button variant="secondary" className="w-full">Statement</Button>
                    </Link>
                  </div>
                )}
              </div>
            )}
          </Card>

          {active && can(me, 'owner', 'accountant') && <ReturnCard sale={s} onDone={refresh} />}

          {active && can(me, 'owner') && (
            <Card title="Cancel bill">
              {!confirming ? (
                <Button variant="secondary" className="w-full" onClick={() => setConfirming(true)}>
                  Cancel bill…
                </Button>
              ) : (
                <form
                  className="space-y-2"
                  onSubmit={(e) => {
                    e.preventDefault()
                    cancel.mutate()
                  }}
                >
                  <p className="text-sm text-stone-600">
                    The bill number stays on record as cancelled and the bags go back into stock.
                  </p>
                  <Input autoFocus required minLength={3} placeholder="Reason" value={reason} onChange={(e) => setReason(e.target.value)} />
                  <ErrorText error={cancel.error} />
                  <div className="flex gap-2">
                    <Button type="submit" className="flex-1 bg-red-600 hover:bg-red-700" disabled={cancel.isPending}>
                      Confirm cancel
                    </Button>
                    <Button type="button" variant="ghost" onClick={() => setConfirming(false)}>
                      Keep
                    </Button>
                  </div>
                </form>
              )}
            </Card>
          )}
        </div>
      </div>
    </>
  )
}
