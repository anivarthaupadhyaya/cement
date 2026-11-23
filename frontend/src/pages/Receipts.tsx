import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom'

import { api } from '../api/client'
import type { Receipt, Shop } from '../api/types'
import { PAY_MODE_LABELS } from '../api/types'
import { Badge, Button, Card, ErrorText, Input, PageHeader } from '../components/ui'
import { useMe } from '../lib/auth'
import { formatDate, formatINR } from '../lib/format'
import { can } from '../lib/roles'
import { useDebounced } from '../lib/useDebounced'

export function ChequeBadge({ status }: { status: Receipt['cheque_status'] }) {
  if (!status) return null
  const tone = { received: 'amber', deposited: 'amber', cleared: 'green', bounced: 'red' } as const
  return <Badge tone={tone[status]}>{status[0].toUpperCase() + status.slice(1)}</Badge>
}

export function ReceiptsPage() {
  const navigate = useNavigate()
  const [search, setSearch] = useState('')
  const q = useDebounced(search)
  const receipts = useQuery({
    queryKey: ['receipts', q],
    queryFn: () => api.get<Receipt[]>(`/api/receipts?limit=200${q ? `&q=${encodeURIComponent(q)}` : ''}`),
  })
  return (
    <>
      <PageHeader
        title="Receipts"
        subtitle="Payments received from customers."
        actions={
          <Link to="/receipts/new">
            <Button>Receive payment</Button>
          </Link>
        }
      />
      <Card>
        <Input className="mb-3 max-w-xs" placeholder="Search receipt no., customer or cheque" value={search} onChange={(e) => setSearch(e.target.value)} />
        <ErrorText error={receipts.error} />
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-left text-stone-500">
              <tr>
                <th className="py-2">Receipt</th>
                <th>Date</th>
                <th>Customer</th>
                <th>Mode</th>
                <th className="text-right">Amount</th>
                <th />
              </tr>
            </thead>
            <tbody className="divide-y divide-stone-100">
              {receipts.data?.map((r) => (
                <tr
                  key={r.id}
                  onClick={() => navigate(`/receipts/${r.id}`)}
                  className={`cursor-pointer hover:bg-stone-50 ${r.status === 'cancelled' || r.cheque_status === 'bounced' ? 'text-stone-400' : ''}`}
                >
                  <td className="py-2 font-mono text-xs">{r.receipt_no}</td>
                  <td>{formatDate(r.receipt_date)}</td>
                  <td className="font-medium">{r.party_name}</td>
                  <td>
                    {PAY_MODE_LABELS[r.mode]} <ChequeBadge status={r.cheque_status} />
                  </td>
                  <td className="text-right tabular-nums">{formatINR(r.amount)}</td>
                  <td className="text-right">{r.status === 'cancelled' && <Badge tone="red">Cancelled</Badge>}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {receipts.data?.length === 0 && <p className="py-6 text-center text-sm text-stone-500">No receipts yet.</p>}
        </div>
      </Card>
    </>
  )
}

export function ReceiptDetailPage() {
  const { id } = useParams()
  const location = useLocation()
  const justSaved = (location.state as { justSaved?: boolean } | null)?.justSaved
  const qc = useQueryClient()
  const { data: me } = useMe()
  const receipt = useQuery({ queryKey: ['receipt', id], queryFn: () => api.get<Receipt>(`/api/receipts/${id}`) })
  const shop = useQuery({ queryKey: ['shop'], queryFn: () => api.get<Shop>('/api/shop') })

  const [reason, setReason] = useState('')
  const [charge, setCharge] = useState('')
  const done = (r: Receipt) => {
    qc.setQueryData(['receipt', id], r)
    qc.invalidateQueries({ queryKey: ['receipts'] })
    qc.invalidateQueries({ queryKey: ['outstanding'] })
    qc.invalidateQueries({ queryKey: ['cheques'] })
  }
  const cancel = useMutation({ mutationFn: () => api.post<Receipt>(`/api/receipts/${id}/cancel`, { reason }), onSuccess: done })
  const cheque = useMutation({
    mutationFn: (action: 'deposit' | 'clear' | 'bounce') =>
      api.post<Receipt>(`/api/receipts/${id}/cheque`, { action, charge: action === 'bounce' && charge.trim() ? charge.trim() : '0' }),
    onSuccess: done,
  })

  if (receipt.isLoading) return <p className="text-stone-500">Loading…</p>
  if (receipt.error || !receipt.data) return <ErrorText error={receipt.error} />
  const r = receipt.data
  const live = r.status === 'active' && r.cheque_status !== 'bounced'

  return (
    <>
      <div className="print:hidden">
        {justSaved && (
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-lg bg-green-50 px-4 py-3 text-green-800">
            <span>
              Receipt <b>{r.receipt_no}</b> saved · {formatINR(r.amount)} · balance now {formatINR(r.balance_after)}
            </span>
            <Link to="/receipts/new">
              <Button>Next receipt</Button>
            </Link>
          </div>
        )}
        <PageHeader
          title={r.receipt_no}
          subtitle={`${formatDate(r.receipt_date)} · ${r.party_name}`}
          actions={
            <div className="flex gap-2">
              <Button variant={justSaved ? 'primary' : 'secondary'} onClick={() => window.print()}>
                Print receipt
              </Button>
              <Link to={`/parties/${r.party_id}/ledger`}>
                <Button variant="secondary">Statement</Button>
              </Link>
            </div>
          }
        />
      </div>

      <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
        {/* Printable receipt */}
        <div className="rounded-lg border border-stone-300 bg-white p-6 print:border-black">
          <div className="mb-4 border-b border-stone-300 pb-3 text-center">
            <div className="text-xs font-semibold tracking-widest">PAYMENT RECEIPT</div>
            <div className="text-xl font-bold">{shop.data?.name}</div>
            <div className="text-sm">{shop.data?.address}</div>
          </div>
          {r.status === 'cancelled' && <p className="mb-2 font-bold text-red-600">CANCELLED: {r.cancel_reason}</p>}
          {r.cheque_status === 'bounced' && <p className="mb-2 font-bold text-red-600">CHEQUE BOUNCED</p>}
          <div className="grid gap-1 text-sm sm:grid-cols-2">
            <div>
              Receipt no.: <b>{r.receipt_no}</b>
            </div>
            <div>Date: {formatDate(r.receipt_date)}</div>
            <div className="sm:col-span-2">
              Received from: <b>{r.party_name}</b>
            </div>
            <div>
              Mode: {PAY_MODE_LABELS[r.mode]}
              {r.cheque_no && ` no. ${r.cheque_no}`}
              {r.cheque_date && ` dated ${formatDate(r.cheque_date)}`}
              {r.bank_name && `, ${r.bank_name}`}
              {r.reference && ` · Ref ${r.reference}`}
            </div>
            <div className="text-right text-lg font-bold sm:text-left">{formatINR(r.amount)}</div>
            <div className="sm:col-span-2 italic">{r.amount_in_words}</div>
          </div>
          {r.allocations.length > 0 && (
            <table className="mt-4 w-full text-sm">
              <thead className="text-left text-stone-500">
                <tr>
                  <th className="py-1">Against bill</th>
                  <th className="text-right">Amount</th>
                </tr>
              </thead>
              <tbody>
                {r.allocations.map((a) => (
                  <tr key={`${a.kind}-${a.id}`} className="border-t border-stone-200">
                    <td className="py-1 font-mono text-xs">{a.ref_no}</td>
                    <td className="text-right tabular-nums">{formatINR(a.amount)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {Number(r.unallocated) > 0 && <p className="mt-2 text-sm">Kept as advance: {formatINR(r.unallocated)}</p>}
          <p className="mt-3 text-sm">
            Balance due after this payment: <b>{formatINR(r.balance_after)}</b>
          </p>
          <div className="mt-10 text-right text-sm">For {shop.data?.name}</div>
        </div>

        <div className="space-y-6 print:hidden">
          {r.mode === 'cheque' && r.status === 'active' && can(me, 'owner', 'accountant') && (
            <Card title="Cheque">
              <div className="mb-3 flex items-center gap-2 text-sm">
                Status: <ChequeBadge status={r.cheque_status} />
              </div>
              {(r.cheque_status === 'received' || r.cheque_status === 'deposited') && (
                <div className="space-y-2">
                  <div className="flex gap-2">
                    {r.cheque_status === 'received' && (
                      <Button variant="secondary" className="flex-1" onClick={() => cheque.mutate('deposit')}>
                        Deposited
                      </Button>
                    )}
                    <Button className="flex-1" onClick={() => cheque.mutate('clear')}>
                      Cleared
                    </Button>
                  </div>
                  <div className="flex gap-2">
                    <Input placeholder="Bounce charge ₹ (optional)" inputMode="decimal" value={charge} onChange={(e) => setCharge(e.target.value)} />
                    <Button className="bg-red-600 hover:bg-red-700" onClick={() => cheque.mutate('bounce')}>
                      Bounced
                    </Button>
                  </div>
                </div>
              )}
              <ErrorText error={cheque.error} />
            </Card>
          )}
          {live && can(me, 'owner') && (
            <Card title="Cancel receipt">
              <form
                className="space-y-2"
                onSubmit={(e) => {
                  e.preventDefault()
                  cancel.mutate()
                }}
              >
                <p className="text-sm text-stone-600">The bills it paid become due again.</p>
                <Input required minLength={3} placeholder="Reason" value={reason} onChange={(e) => setReason(e.target.value)} />
                <ErrorText error={cancel.error} />
                <Button type="submit" variant="secondary" className="w-full" disabled={cancel.isPending}>
                  Cancel receipt
                </Button>
              </form>
            </Card>
          )}
        </div>
      </div>
    </>
  )
}
