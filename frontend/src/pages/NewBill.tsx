import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { api, ApiError } from '../api/client'
import type { BillPreview, Party, Product, Quote, Sale } from '../api/types'
import { CustomerPicker } from '../components/CustomerPicker'
import { Badge, Button, Card, ErrorText, Field, Input, PageHeader, Select } from '../components/ui'
import { cx } from '../lib/cx'
import { useMe } from '../lib/auth'
import { formatINR, toPaise } from '../lib/format'
import { newClientRef } from '../lib/ids'
import { can } from '../lib/roles'
import { useDebounced } from '../lib/useDebounced'

interface Line {
  key: number
  product_id: string
  qty: string
  rate: string
  rateTouched: boolean
  rateSource?: 'party' | 'list'
}

let nextKey = 1
const blankLine = (): Line => ({ key: nextKey++, product_id: '', qty: '', rate: '', rateTouched: false })
const validQty = (v: string) => /^[1-9]\d*$/.test(v.trim())
const validRate = (v: string) => toPaise(v) > 0

function focus(selector: string) {
  setTimeout(() => document.querySelector<HTMLElement>(selector)?.focus(), 0)
}

export function NewBillPage() {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const { data: me } = useMe()
  const isOwner = can(me, 'owner')

  const products = useQuery({ queryKey: ['products', 'active'], queryFn: () => api.get<Product[]>('/api/products?active=true') })

  const [clientRef, setClientRef] = useState(newClientRef)
  const [party, setParty] = useState<Party | null>(null)
  const [walkIn, setWalkIn] = useState({ name: '', phone: '' })
  const [mode, setMode] = useState<'cash' | 'credit'>('cash')
  const [lines, setLines] = useState<Line[]>([blankLine()])
  const [extra, setExtra] = useState({ delivery_charge: '', vehicle_no: '', delivery_address: '', notes: '' })
  const [overrideReason, setOverrideReason] = useState('')

  const setLine = (key: number, patch: Partial<Line>) =>
    setLines((ls) => ls.map((l) => (l.key === key ? { ...l, ...patch } : l)))

  // Credit is only possible for a named customer who has a credit limit.
  useEffect(() => {
    if (!party) setMode('cash')
    else if (Number(party.credit_limit) > 0) setMode('credit')
  }, [party])

  // Fill rates from the rate card (or the customer's special rate) unless the user typed one.
  const fillRate = useCallback(
    async (line: Line, partyId: number | null) => {
      if (!line.product_id || line.rateTouched) return
      try {
        const q = await api.get<Quote>(
          `/api/prices/quote?product_id=${line.product_id}${partyId ? `&party_id=${partyId}` : ''}`,
        )
        setLine(line.key, { rate: q.rate, rateSource: q.source })
      } catch {
        setLine(line.key, { rate: '', rateSource: undefined })
      }
    },
    [],
  )
  useEffect(() => {
    lines.forEach((l) => fillRate(l, party?.id ?? null))
    // Re-quote when the customer changes (special rates); line changes call fillRate directly.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [party?.id])

  const complete = lines.filter((l) => l.product_id && validQty(l.qty) && validRate(l.rate))
  const deliveryOk = extra.delivery_charge.trim() === '' || toPaise(extra.delivery_charge) >= 0
  const draft = {
    party_id: party?.id ?? null,
    customer_name: party ? null : walkIn.name.trim() || null,
    payment_mode: mode,
    godown_id: 1,
    delivery_charge: extra.delivery_charge.trim() || '0',
    lines: complete.map((l) => ({ product_id: Number(l.product_id), qty: Number(l.qty), rate: l.rate.trim() })),
  }
  // Debounce the JSON, not the object: a new object every render would never settle.
  const debouncedJson = useDebounced(JSON.stringify(draft), 300)
  const preview = useQuery({
    queryKey: ['bill-preview', debouncedJson],
    queryFn: () => api.post<BillPreview>('/api/sales/preview', JSON.parse(debouncedJson)),
    enabled: draft.lines.length > 0 && deliveryOk,
    placeholderData: (prev) => prev,
  })
  const p = preview.data
  const previewByProduct = new Map(p?.lines.map((l) => [l.product_id, l]))

  const incomplete = lines.some((l) => (l.product_id || l.qty) && !(l.product_id && validQty(l.qty) && validRate(l.rate)))
  const duplicate = new Set(lines.filter((l) => l.product_id).map((l) => l.product_id)).size !== lines.filter((l) => l.product_id).length
  const needsReason = !!p?.over_limit && mode === 'credit'
  const blocked =
    complete.length === 0 ||
    incomplete ||
    duplicate ||
    !deliveryOk ||
    (needsReason && (!isOwner || overrideReason.trim().length < 3)) ||
    (!!p && p.lines.some((l) => l.available < l.qty))

  const save = useMutation({
    mutationFn: () =>
      api.post<Sale>('/api/sales', {
        ...draft,
        client_ref: clientRef,
        customer_phone: party ? null : walkIn.phone.trim() || null,
        vehicle_no: extra.vehicle_no.trim() || null,
        delivery_address: extra.delivery_address.trim() || null,
        notes: extra.notes.trim() || null,
        credit_override_reason: needsReason ? overrideReason.trim() : null,
      }),
    onSuccess: (sale) => {
      qc.invalidateQueries({ queryKey: ['sales'] })
      qc.invalidateQueries({ queryKey: ['stock'] })
      navigate(`/sales/${sale.id}`, { state: { justSaved: true } })
    },
    onError: (err) => {
      // A rejected bill was never saved, so a fresh attempt can reuse the same reference.
      if (err instanceof ApiError && err.status >= 500) setClientRef(newClientRef())
    },
  })

  const trySave = () => {
    if (!blocked && !save.isPending) save.mutate()
  }

  // Ctrl+Enter or F9 saves from anywhere on the screen.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey && e.key === 'Enter') || e.key === 'F9') {
        e.preventDefault()
        trySave()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  })

  const addLine = () => {
    const l = blankLine()
    setLines((ls) => [...ls, l])
    focus(`[data-line="${l.key}"] select`)
  }

  return (
    <>
      <PageHeader
        title="New bill"
        subtitle="Rates are per bag including GST. Enter moves to the next box; Ctrl+Enter or F9 saves."
      />
      <div className="grid gap-6 xl:grid-cols-[1fr_360px]">
        <div className="space-y-6">
          <Card title="Customer">
            <CustomerPicker value={party} onChange={setParty} autoFocus />
            {!party && (
              <div className="mt-3 grid grid-cols-2 gap-3">
                <Field label="Walk-in name (optional)">
                  <Input value={walkIn.name} onChange={(e) => setWalkIn({ ...walkIn, name: e.target.value })} placeholder="Cash customer" />
                </Field>
                <Field label="Phone (optional)">
                  <Input inputMode="tel" value={walkIn.phone} onChange={(e) => setWalkIn({ ...walkIn, phone: e.target.value })} />
                </Field>
              </div>
            )}
            <div className="mt-3 flex items-center gap-2">
              {(['cash', 'credit'] as const).map((m) => (
                <button
                  key={m}
                  type="button"
                  disabled={m === 'credit' && !party}
                  onClick={() => setMode(m)}
                  className={cx(
                    'rounded-md border px-4 py-1.5 text-sm font-medium',
                    mode === m ? 'border-brand-600 bg-brand-600 text-white' : 'border-stone-300 bg-white text-stone-700',
                    m === 'credit' && !party && 'cursor-not-allowed opacity-40',
                  )}
                >
                  {m === 'cash' ? 'Cash / paid now' : 'Credit (udhaar)'}
                </button>
              ))}
              {p?.outstanding != null && (
                <span className="ml-auto text-sm text-stone-600">
                  Due now: <b className="tabular-nums">{formatINR(p.outstanding)}</b>
                  {p.credit_limit != null && Number(p.credit_limit) > 0 && <> of {formatINR(p.credit_limit)}</>}
                </span>
              )}
            </div>
          </Card>

          <Card title="Bags">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="text-left text-stone-500">
                  <tr>
                    <th className="py-2">Product</th>
                    <th className="w-24 text-right">Bags</th>
                    <th className="w-32 text-right">Rate / bag</th>
                    <th className="w-28 text-right">In stock</th>
                    <th className="w-32 text-right">Amount</th>
                    <th className="w-8" />
                  </tr>
                </thead>
                <tbody className="divide-y divide-stone-100">
                  {lines.map((l, i) => {
                    const pl = previewByProduct.get(Number(l.product_id))
                    const short = pl && pl.available < pl.qty
                    return (
                      <tr key={l.key} data-line={l.key} className="align-top">
                        <td className="py-1.5 pr-2">
                          <Select
                            value={l.product_id}
                            onChange={(e) => {
                              const next = { ...l, product_id: e.target.value, rateTouched: false }
                              setLine(l.key, next)
                              fillRate(next, party?.id ?? null)
                              focus(`[data-line="${l.key}"] [data-qty]`)
                            }}
                          >
                            <option value="">Choose product…</option>
                            {products.data?.map((pr) => (
                              <option key={pr.id} value={pr.id}>
                                {pr.name}
                              </option>
                            ))}
                          </Select>
                          {pl?.below_cost && <span className="text-xs text-red-600">Below cost</span>}
                        </td>
                        <td className="py-1.5 pl-2">
                          <Input
                            data-qty
                            className="text-right tabular-nums"
                            inputMode="numeric"
                            value={l.qty}
                            onChange={(e) => setLine(l.key, { qty: e.target.value })}
                            onKeyDown={(e) => {
                              if (e.key === 'Enter') {
                                e.preventDefault()
                                focus(`[data-line="${l.key}"] [data-rate]`)
                              }
                            }}
                          />
                        </td>
                        <td className="py-1.5 pl-2">
                          <Input
                            data-rate
                            className="text-right tabular-nums"
                            inputMode="decimal"
                            value={l.rate}
                            onChange={(e) => setLine(l.key, { rate: e.target.value, rateTouched: true, rateSource: undefined })}
                            onKeyDown={(e) => {
                              if (e.key === 'Enter') {
                                e.preventDefault()
                                if (i === lines.length - 1) addLine()
                                else focus(`[data-line="${lines[i + 1].key}"] select`)
                              }
                            }}
                          />
                          {l.rateSource === 'party' && <span className="text-xs text-brand-700">Special rate</span>}
                        </td>
                        <td className={cx('py-3 text-right tabular-nums', short ? 'font-semibold text-red-600' : 'text-stone-500')}>
                          {pl ? pl.available : '—'}
                        </td>
                        <td className="py-3 text-right font-medium tabular-nums">{pl ? formatINR(pl.gross) : '—'}</td>
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
            <Button type="button" variant="secondary" className="mt-3" onClick={addLine}>
              + Add product
            </Button>
          </Card>

          <Card title="Delivery">
            <div className="grid gap-3 sm:grid-cols-3">
              <Field label="Delivery charge (incl. GST)">
                <Input inputMode="decimal" value={extra.delivery_charge} onChange={(e) => setExtra({ ...extra, delivery_charge: e.target.value })} placeholder="0" />
              </Field>
              <Field label="Vehicle no.">
                <Input className="uppercase" value={extra.vehicle_no} onChange={(e) => setExtra({ ...extra, vehicle_no: e.target.value })} />
              </Field>
              <Field label="Notes">
                <Input value={extra.notes} onChange={(e) => setExtra({ ...extra, notes: e.target.value })} />
              </Field>
            </div>
            <div className="mt-3">
              <Field label="Deliver to (site address)">
                <Input value={extra.delivery_address} onChange={(e) => setExtra({ ...extra, delivery_address: e.target.value })} />
              </Field>
            </div>
          </Card>
        </div>

        <div className="xl:sticky xl:top-6 xl:self-start">
          <Card title="Bill total">
            {!p ? (
              <p className="text-sm text-stone-500">Add a product, bags and rate to see the total.</p>
            ) : (
              <dl className="space-y-1.5 text-sm">
                <div className="flex justify-between">
                  <dt className="text-stone-500">{p.total_bags} bags · taxable</dt>
                  <dd className="tabular-nums">{formatINR(p.taxable_total)}</dd>
                </div>
                {p.is_interstate ? (
                  <div className="flex justify-between">
                    <dt className="text-stone-500">IGST</dt>
                    <dd className="tabular-nums">{formatINR(p.igst_total)}</dd>
                  </div>
                ) : (
                  <>
                    <div className="flex justify-between">
                      <dt className="text-stone-500">CGST</dt>
                      <dd className="tabular-nums">{formatINR(p.cgst_total)}</dd>
                    </div>
                    <div className="flex justify-between">
                      <dt className="text-stone-500">SGST</dt>
                      <dd className="tabular-nums">{formatINR(p.sgst_total)}</dd>
                    </div>
                  </>
                )}
                <div className="flex justify-between">
                  <dt className="text-stone-500">Round off</dt>
                  <dd className="tabular-nums">{formatINR(p.round_off)}</dd>
                </div>
                <div className="flex justify-between border-t border-stone-200 pt-2 text-2xl font-bold">
                  <dt>Total</dt>
                  <dd className="tabular-nums">{formatINR(p.grand_total)}</dd>
                </div>
                {p.margin !== null && (
                  <div className="flex justify-between pt-1">
                    <dt className="text-stone-500">Margin</dt>
                    <dd className={cx('font-medium tabular-nums', Number(p.margin) < 0 ? 'text-red-600' : 'text-green-700')}>
                      {formatINR(p.margin)}
                      {p.total_bags > 0 && (
                        <span className="text-xs text-stone-500"> ({formatINR((Number(p.margin) / p.total_bags).toFixed(2))}/bag)</span>
                      )}
                    </dd>
                  </div>
                )}
              </dl>
            )}

            {p && p.warnings.length > 0 && (
              <ul className="mt-3 space-y-1">
                {p.warnings.map((w) => (
                  <li key={w} className="rounded bg-amber-50 px-2 py-1 text-xs text-amber-800">
                    {w}
                  </li>
                ))}
              </ul>
            )}

            {needsReason && (
              <div className="mt-3">
                {isOwner ? (
                  <Field label="Reason for going over the credit limit">
                    <Input value={overrideReason} onChange={(e) => setOverrideReason(e.target.value)} placeholder="e.g. regular payer, approved" />
                  </Field>
                ) : (
                  <p className="rounded bg-red-50 px-2 py-1 text-sm text-red-700">
                    Over the credit limit: ask the owner, or bill as cash.
                  </p>
                )}
              </div>
            )}

            <ErrorText error={preview.error} />
            <div className="mt-3">
              <ErrorText error={save.error} />
            </div>
            <Button className="mt-4 w-full py-3 text-base" onClick={trySave} disabled={blocked || save.isPending}>
              {save.isPending ? 'Saving…' : 'Save bill (Ctrl+Enter)'}
            </Button>
            <div className="mt-2 flex items-center justify-center gap-2 text-xs text-stone-500">
              {mode === 'credit' ? <Badge tone="amber">Credit bill</Badge> : <Badge tone="green">Cash bill</Badge>}
              {p?.is_interstate && <Badge>Inter-state · IGST</Badge>}
            </div>
          </Card>
        </div>
      </div>
    </>
  )
}
