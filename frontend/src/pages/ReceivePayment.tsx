import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'

import { api, ApiError } from '../api/client'
import type { Party, PayMode, Receipt, ReceiptPreview } from '../api/types'
import { PAY_MODE_LABELS } from '../api/types'
import { CustomerPicker } from '../components/CustomerPicker'
import { Badge, Button, Card, ErrorText, Field, Input, PageHeader } from '../components/ui'
import { useMe } from '../lib/auth'
import { cx } from '../lib/cx'
import { formatDate, formatINR, paiseToRupees, todayISO, toPaise } from '../lib/format'
import { newClientRef } from '../lib/ids'
import { can } from '../lib/roles'
import { useDebounced } from '../lib/useDebounced'

export function ReceivePaymentPage() {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [params] = useSearchParams()
  const { data: me } = useMe()
  const office = can(me, 'owner', 'accountant')
  const modes: PayMode[] = office ? ['cash', 'upi', 'bank', 'cheque'] : ['cash', 'upi']

  const [clientRef, setClientRef] = useState(newClientRef)
  const [party, setParty] = useState<Party | null>(null)
  const [amount, setAmount] = useState('')
  const [mode, setMode] = useState<PayMode>('cash')
  const [details, setDetails] = useState({ reference: '', cheque_no: '', cheque_date: todayISO(), bank_name: '', notes: '' })
  const [manual, setManual] = useState(false)
  const [split, setSplit] = useState<Record<string, string>>({})

  // Arriving from the outstanding list: /receipts/new?party=12
  const preset = params.get('party')
  useEffect(() => {
    if (preset && !party) api.get<Party>(`/api/parties/${preset}`).then(setParty).catch(() => undefined)
  }, [preset, party])

  const amountPaise = toPaise(amount)
  const amountOk = amountPaise > 0
  const debounced = useDebounced(JSON.stringify({ party_id: party?.id, amount: amountOk ? amount.trim() : '1' }), 250)
  const preview = useQuery({
    queryKey: ['receipt-preview', debounced],
    queryFn: () => api.post<ReceiptPreview>('/api/receipts/preview', JSON.parse(debounced)),
    enabled: !!party,
    placeholderData: (prev) => prev,
  })
  const p = preview.data

  const planFor = (key: string) => p?.plan.find((x) => `${x.kind}-${x.id}` === key)?.amount
  const manualTotal = Object.values(split).reduce((a, v) => a + (toPaise(v) > 0 ? toPaise(v) : 0), 0)
  const manualBad =
    manual &&
    (manualTotal > amountPaise ||
      Object.entries(split).some(([key, v]) => {
        if (!v.trim()) return false
        const item = p?.open_items.find((i) => `${i.kind}-${i.id}` === key)
        return !(toPaise(v) > 0) || !item || toPaise(v) > toPaise(item.balance)
      }))

  const chequeOk = mode !== 'cheque' || details.cheque_no.trim().length > 0
  const canSave = !!party && amountOk && chequeOk && !manualBad

  const save = useMutation({
    mutationFn: () =>
      api.post<Receipt>('/api/receipts', {
        client_ref: clientRef,
        party_id: party!.id,
        amount: amount.trim(),
        mode,
        reference: details.reference.trim() || null,
        cheque_no: mode === 'cheque' ? details.cheque_no.trim() : null,
        cheque_date: mode === 'cheque' ? details.cheque_date : null,
        bank_name: mode === 'cheque' ? details.bank_name.trim() || null : null,
        notes: details.notes.trim() || null,
        allocations: manual
          ? Object.entries(split)
              .filter(([, v]) => toPaise(v) > 0)
              .map(([key, v]) => {
                const [kind, id] = key.split('-')
                return { kind, id: Number(id), amount: v.trim() }
              })
          : null,
      }),
    onSuccess: (r) => {
      qc.invalidateQueries({ queryKey: ['receipts'] })
      qc.invalidateQueries({ queryKey: ['outstanding'] })
      navigate(`/receipts/${r.id}`, { state: { justSaved: true } })
    },
    onError: (err) => {
      if (err instanceof ApiError && err.status >= 500) setClientRef(newClientRef())
    },
  })

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey && e.key === 'Enter') || e.key === 'F9') {
        e.preventDefault()
        if (canSave && !save.isPending) save.mutate()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  })

  const fillAll = () => p && setAmount(p.outstanding)

  return (
    <>
      <PageHeader title="Receive payment" subtitle="Settles the oldest bills first unless you split it yourself. Ctrl+Enter saves." />
      <div className="grid gap-6 xl:grid-cols-[1fr_360px]">
        <div className="space-y-6">
          <Card title="From">
            <CustomerPicker
              value={party}
              onChange={(pt) => {
                setParty(pt)
                setSplit({})
              }}
              autoFocus={!preset}
            />
            {p && p.bounced_cheques > 0 && (
              <p className="mt-2 rounded bg-red-50 px-2 py-1 text-sm text-red-700">
                {p.bounced_cheques} cheque(s) from this customer bounced before.
              </p>
            )}
          </Card>

          {party && (
            <Card title="Open bills (oldest first)">
              {p?.open_items.length === 0 ? (
                <p className="text-sm text-stone-500">Nothing due. Any payment will be kept as an advance.</p>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead className="text-left text-stone-500">
                      <tr>
                        <th className="py-2">Bill</th>
                        <th>Date</th>
                        <th className="text-right">Age</th>
                        <th className="text-right">Bill amount</th>
                        <th className="text-right">Already paid</th>
                        <th className="text-right">Due</th>
                        <th className="w-36 text-right">This payment</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-stone-100">
                      {p?.open_items.map((i) => {
                        const key = `${i.kind}-${i.id}`
                        const suggested = amountOk ? planFor(key) : undefined
                        return (
                          <tr key={key}>
                            <td className="py-2 font-mono text-xs">
                              {i.ref_no} {i.kind === 'due' && <Badge>Old due</Badge>}
                            </td>
                            <td>{formatDate(i.date)}</td>
                            <td className={cx('text-right tabular-nums', i.age_days > 90 ? 'font-semibold text-red-600' : i.age_days > 30 ? 'text-amber-700' : '')}>
                              {i.age_days}d
                            </td>
                            <td className="text-right tabular-nums">{formatINR(i.amount)}</td>
                            <td className="text-right tabular-nums text-stone-500">{formatINR(i.paid)}</td>
                            <td className="text-right font-medium tabular-nums">{formatINR(i.balance)}</td>
                            <td className="py-1 text-right">
                              {manual ? (
                                <Input
                                  className="text-right tabular-nums"
                                  inputMode="decimal"
                                  value={split[key] ?? ''}
                                  onChange={(e) => setSplit({ ...split, [key]: e.target.value })}
                                />
                              ) : (
                                <span className="tabular-nums text-green-700">{suggested ? formatINR(suggested) : ''}</span>
                              )}
                            </td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </div>
              )}
              {!!p?.open_items.length && (
                <label className="mt-3 flex items-center gap-2 text-sm text-stone-600">
                  <input type="checkbox" checked={manual} onChange={(e) => setManual(e.target.checked)} />
                  Split across bills myself
                  {manual && (
                    <span className={cx('ml-auto tabular-nums', manualBad ? 'text-red-600' : '')}>
                      Split {formatINR(paiseToRupees(manualTotal))} of {formatINR(amountOk ? amount : '0')}
                    </span>
                  )}
                </label>
              )}
            </Card>
          )}
        </div>

        <div className="space-y-6 xl:sticky xl:top-6 xl:self-start">
          <Card title="Payment">
            <div className="space-y-3">
              {p && (
                <div className="flex items-center justify-between rounded-md bg-stone-50 px-3 py-2 text-sm">
                  <span className="text-stone-600">{Number(p.outstanding) < 0 ? 'Advance held' : 'Total due'}</span>
                  <button type="button" className="font-semibold tabular-nums hover:underline" onClick={fillAll} title="Use full amount">
                    {formatINR(p.outstanding.replace('-', ''))}
                  </button>
                </div>
              )}
              <Field label="Amount received (₹)">
                <Input
                  className="text-xl font-semibold tabular-nums"
                  inputMode="decimal"
                  value={amount}
                  onChange={(e) => setAmount(e.target.value)}
                  autoFocus={!!preset}
                />
              </Field>
              <div className="flex flex-wrap gap-2">
                {modes.map((m) => (
                  <button
                    key={m}
                    type="button"
                    onClick={() => setMode(m)}
                    className={cx(
                      'rounded-md border px-3 py-1.5 text-sm font-medium',
                      mode === m ? 'border-brand-600 bg-brand-600 text-white' : 'border-stone-300 bg-white',
                    )}
                  >
                    {PAY_MODE_LABELS[m]}
                  </button>
                ))}
              </div>
              {(mode === 'upi' || mode === 'bank') && (
                <Field label={mode === 'upi' ? 'UPI reference (optional)' : 'UTR / reference'}>
                  <Input value={details.reference} onChange={(e) => setDetails({ ...details, reference: e.target.value })} />
                </Field>
              )}
              {mode === 'cheque' && (
                <div className="grid grid-cols-2 gap-3">
                  <Field label="Cheque no.">
                    <Input value={details.cheque_no} onChange={(e) => setDetails({ ...details, cheque_no: e.target.value })} />
                  </Field>
                  <Field label="Cheque date">
                    <Input type="date" value={details.cheque_date} onChange={(e) => setDetails({ ...details, cheque_date: e.target.value })} />
                  </Field>
                  <div className="col-span-2">
                    <Field label="Bank">
                      <Input value={details.bank_name} onChange={(e) => setDetails({ ...details, bank_name: e.target.value })} />
                    </Field>
                  </div>
                </div>
              )}
              <Field label="Notes">
                <Input value={details.notes} onChange={(e) => setDetails({ ...details, notes: e.target.value })} />
              </Field>
              {p && amountOk && !manual && Number(p.advance_after) > 0 && (
                <p className="rounded bg-amber-50 px-2 py-1 text-xs text-amber-800">
                  {formatINR(p.advance_after)} more than the dues; it will be kept as an advance.
                </p>
              )}
              <ErrorText error={save.error} />
              <Button className="w-full py-3 text-base" disabled={!canSave || save.isPending} onClick={() => save.mutate()}>
                {save.isPending ? 'Saving…' : 'Save receipt (Ctrl+Enter)'}
              </Button>
            </div>
          </Card>
        </div>
      </div>
    </>
  )
}
