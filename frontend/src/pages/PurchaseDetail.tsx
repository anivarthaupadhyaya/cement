import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { api } from '../api/client'
import type { Purchase } from '../api/types'
import { Badge, Button, Card, ErrorText, Input, PageHeader } from '../components/ui'
import { useMe } from '../lib/auth'
import { formatDate, formatINR, paiseToRupees, toPaise } from '../lib/format'
import { can } from '../lib/roles'

function Row({ label, value, strong }: { label: string; value: string; strong?: boolean }) {
  return (
    <div className={`flex justify-between ${strong ? 'border-t border-stone-200 pt-2 text-base font-semibold' : ''}`}>
      <dt className={strong ? '' : 'text-stone-500'}>{label}</dt>
      <dd className="tabular-nums">{value}</dd>
    </div>
  )
}

export function PurchaseDetailPage() {
  const { id } = useParams()
  const qc = useQueryClient()
  const { data: me } = useMe()
  const purchase = useQuery({ queryKey: ['purchase', id], queryFn: () => api.get<Purchase>(`/api/purchases/${id}`) })

  const [reason, setReason] = useState('')
  const [confirming, setConfirming] = useState(false)
  const cancel = useMutation({
    mutationFn: () => api.post<Purchase>(`/api/purchases/${id}/cancel`, { reason }),
    onSuccess: (p) => {
      qc.setQueryData(['purchase', id], p)
      qc.invalidateQueries({ queryKey: ['purchases'] })
      qc.invalidateQueries({ queryKey: ['stock'] })
      setConfirming(false)
    },
  })

  if (purchase.isLoading) return <p className="text-stone-500">Loading…</p>
  if (purchase.error || !purchase.data) return <ErrorText error={purchase.error} />
  const p = purchase.data
  const charges = paiseToRupees(toPaise(p.freight) + toPaise(p.unloading) + toPaise(p.other_charges))
  const damagedOrShort = p.lines.some((l) => l.qty_damaged > 0 || l.qty_short > 0)

  return (
    <>
      <PageHeader
        title={`${p.supplier_name} · ${p.supplier_invoice_no}`}
        subtitle={`Bill dated ${formatDate(p.invoice_date)}, received ${formatDate(p.received_date)} into ${p.godown_name}`}
        actions={
          <div className="flex items-center gap-2">
            {p.status === 'cancelled' && <Badge tone="red">Cancelled</Badge>}
            <Link to="/purchases">
              <Button variant="secondary">Back</Button>
            </Link>
          </div>
        }
      />
      {p.status === 'cancelled' && (
        <p className="mb-4 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">
          Cancelled: {p.cancel_reason}. The bags were taken back out of stock.
        </p>
      )}

      <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
        <Card title="Bags">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-left text-stone-500">
                <tr>
                  <th className="py-2">Product</th>
                  <th className="text-right">Billed</th>
                  <th className="text-right">Good</th>
                  <th className="text-right">Damaged</th>
                  <th className="text-right">Short</th>
                  <th className="text-right">Rate</th>
                  <th className="text-right">GST</th>
                  <th className="text-right">Taxable</th>
                  <th className="text-right" title="(Taxable + share of charges) ÷ good bags">
                    Cost / good bag
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-stone-100">
                {p.lines.map((l) => (
                  <tr key={l.id}>
                    <td className="py-2 font-medium">{l.product_name}</td>
                    <td className="text-right tabular-nums">{l.qty_invoiced}</td>
                    <td className="text-right tabular-nums">{l.qty_received}</td>
                    <td className={`text-right tabular-nums ${l.qty_damaged ? 'text-red-600' : 'text-stone-400'}`}>
                      {l.qty_damaged}
                    </td>
                    <td className={`text-right tabular-nums ${l.qty_short ? 'text-red-600' : 'text-stone-400'}`}>
                      {l.qty_short}
                    </td>
                    <td className="text-right tabular-nums">{formatINR(l.rate)}</td>
                    <td className="text-right tabular-nums">{Number(l.gst_rate)}%</td>
                    <td className="text-right tabular-nums">{formatINR(l.taxable)}</td>
                    <td className="text-right font-semibold tabular-nums">{formatINR(l.landed_cost)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {damagedOrShort && (
            <p className="mt-3 rounded-md bg-amber-50 px-3 py-2 text-sm text-amber-800">
              Damaged or short bags raise the cost of the good ones. Claim them from the supplier.
            </p>
          )}
          <dl className="mt-4 grid gap-x-6 gap-y-1 text-sm text-stone-600 sm:grid-cols-3">
            <div>Truck: {p.vehicle_no ?? '—'}</div>
            <div>LR: {p.lr_no ?? '—'}</div>
            <div>Our charges: {formatINR(charges)}</div>
            {p.notes && <div className="sm:col-span-3">Notes: {p.notes}</div>}
          </dl>
        </Card>

        <div className="space-y-6">
          <Card title="Bill total">
            <dl className="space-y-1.5 text-sm">
              <Row label="Taxable value" value={formatINR(p.taxable_total)} />
              {p.is_interstate ? (
                <Row label="IGST" value={formatINR(p.igst_total)} />
              ) : (
                <>
                  <Row label="CGST" value={formatINR(p.cgst_total)} />
                  <Row label="SGST" value={formatINR(p.sgst_total)} />
                </>
              )}
              <Row label="Round off" value={formatINR(p.round_off)} />
              <Row label="Bill total" value={formatINR(p.invoice_total)} strong />
            </dl>
          </Card>

          {p.status === 'active' && can(me, 'owner') && (
            <Card title="Cancel this purchase">
              {!confirming ? (
                <Button variant="secondary" className="w-full" onClick={() => setConfirming(true)}>
                  Cancel purchase…
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
                    The bags will be taken out of stock. Bills can't be edited, so enter the corrected bill again after
                    cancelling.
                  </p>
                  <Input
                    autoFocus
                    required
                    minLength={3}
                    placeholder="Reason, e.g. wrong rate entered"
                    value={reason}
                    onChange={(e) => setReason(e.target.value)}
                  />
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
