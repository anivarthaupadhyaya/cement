import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

import { api } from '../api/client'
import type { RateCardRow } from '../api/types'
import { Badge, Button, Card, ErrorText, Field, Input, PageHeader } from '../components/ui'
import { useMe } from '../lib/auth'
import { formatDate, formatINR, todayISO } from '../lib/format'
import { can } from '../lib/roles'

const RATE_RE = /^\d{1,10}(\.\d{1,2})?$/

/** Per-bag price before GST, for display. Done in paise so it can't drift. */
function exclGst(rate: string, gst: string | null): string | null {
  if (!gst) return null
  const paise = Math.round(Number(rate) * 100)
  const gstBp = Math.round(Number(gst) * 100) // basis points
  return (Math.round((paise * 10000) / (10000 + gstBp)) / 100).toFixed(2)
}

function Change({ now, before }: { now: string | null; before: string | null }) {
  if (!now || !before) return null
  const diff = Number(now) - Number(before)
  if (diff === 0) return null
  return <Badge tone={diff > 0 ? 'red' : 'green'}>{`${diff > 0 ? '▲' : '▼'} ₹${Math.abs(diff).toFixed(2)}`}</Badge>
}

export function RatesPage() {
  const qc = useQueryClient()
  const { data: me } = useMe()
  const isOwner = can(me, 'owner')

  const [on, setOn] = useState(todayISO())
  const card = useQuery({
    queryKey: ['rate-card', on],
    queryFn: () => api.get<RateCardRow[]>(`/api/prices/card?on=${on}`),
  })

  const [draft, setDraft] = useState<Record<number, string>>({})
  const changed = Object.entries(draft).filter(([id, v]) => {
    const row = card.data?.find((r) => r.product_id === Number(id))
    return v.trim() !== '' && (!row?.rate || Number(v) !== Number(row.rate))
  })
  const invalid = changed.some(([, v]) => !RATE_RE.test(v.trim()) || Number(v) <= 0)

  const save = useMutation({
    mutationFn: () =>
      api.post('/api/prices', {
        effective_from: on,
        items: changed.map(([id, v]) => ({ product_id: Number(id), rate: v.trim() })),
      }),
    onSuccess: () => {
      setDraft({})
      qc.invalidateQueries({ queryKey: ['rate-card'] })
    },
  })

  const focusNext = (index: number) => {
    const next = document.querySelector<HTMLInputElement>(`[data-rate-index="${index + 1}"]`)
    if (next) next.focus()
    else document.querySelector<HTMLButtonElement>('[data-save-rates]')?.focus()
  }

  return (
    <>
      <PageHeader
        title="Today's rates"
        subtitle="Selling rate per bag, including GST. A new rate applies from the chosen date; older bills keep their rate."
      />
      <Card>
        <div className="mb-4 flex flex-wrap items-end gap-3">
          <div className="w-44">
            <Field label="Rates as on">
              <Input type="date" value={on} onChange={(e) => setOn(e.target.value)} />
            </Field>
          </div>
          {isOwner && (
            <Button
              data-save-rates
              onClick={() => save.mutate()}
              disabled={changed.length === 0 || invalid || save.isPending}
            >
              {save.isPending ? 'Saving…' : `Save ${changed.length || ''} rate${changed.length === 1 ? '' : 's'}`}
            </Button>
          )}
          {invalid && <span className="text-sm text-red-600">Enter rates like 385 or 385.50</span>}
        </div>
        <ErrorText error={card.error ?? save.error} />
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-left text-stone-500">
              <tr>
                <th className="py-2">Product</th>
                <th className="text-right">Rate / bag</th>
                <th>Since</th>
                <th>Change</th>
                <th className="text-right">GST</th>
                <th className="text-right">Excl. GST</th>
                {isOwner && <th className="w-36 text-right">New rate</th>}
              </tr>
            </thead>
            <tbody className="divide-y divide-stone-100">
              {card.data?.map((r, i) => (
                <tr key={r.product_id}>
                  <td className="py-2 font-medium">{r.product_name}</td>
                  <td className="text-right text-base font-semibold tabular-nums">{formatINR(r.rate)}</td>
                  <td className="text-stone-500">{formatDate(r.effective_from)}</td>
                  <td>
                    <Change now={r.rate} before={r.previous_rate} />
                  </td>
                  <td className="text-right tabular-nums">{r.gst_rate ? `${Number(r.gst_rate)}%` : '—'}</td>
                  <td className="text-right text-stone-500 tabular-nums">
                    {r.rate ? formatINR(exclGst(r.rate, r.gst_rate)) : '—'}
                  </td>
                  {isOwner && (
                    <td className="py-1 text-right">
                      <Input
                        data-rate-index={i}
                        className="text-right tabular-nums"
                        inputMode="decimal"
                        placeholder={r.rate ?? '0.00'}
                        value={draft[r.product_id] ?? ''}
                        onChange={(e) => setDraft({ ...draft, [r.product_id]: e.target.value })}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') {
                            e.preventDefault()
                            focusNext(i)
                          }
                        }}
                      />
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
          {card.data?.length === 0 && (
            <p className="py-6 text-center text-sm text-stone-500">Add products first, then set their rates here.</p>
          )}
        </div>
      </Card>
    </>
  )
}
