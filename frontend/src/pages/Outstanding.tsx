import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { api } from '../api/client'
import type { Ageing, AgeingRow } from '../api/types'
import { Button, Card, ErrorText, Input, PageHeader } from '../components/ui'
import { cx } from '../lib/cx'
import { formatINR } from '../lib/format'
import { useDebounced } from '../lib/useDebounced'

type SortKey = 'net' | 'overdue' | 'oldest_days' | 'party_name'

const COLS: { key: keyof AgeingRow; label: string; tone?: string }[] = [
  { key: 'b0_30', label: '0–30 days' },
  { key: 'b31_60', label: '31–60', tone: 'text-amber-700' },
  { key: 'b61_90', label: '61–90', tone: 'text-orange-700' },
  { key: 'b90_plus', label: '90+', tone: 'text-red-700 font-semibold' },
]

export function OutstandingPage() {
  const navigate = useNavigate()
  const [area, setArea] = useState('')
  const [sort, setSort] = useState<SortKey>('net')
  const a = useDebounced(area)
  const report = useQuery({
    queryKey: ['outstanding', a],
    queryFn: () => api.get<Ageing>(`/api/reports/outstanding${a ? `?area=${encodeURIComponent(a)}` : ''}`),
  })

  const rows = [...(report.data?.rows ?? [])].sort((x, y) =>
    sort === 'party_name' ? x.party_name.localeCompare(y.party_name) : Number(y[sort]) - Number(x[sort]),
  )
  const t = report.data?.totals

  return (
    <>
      <PageHeader title="Outstanding" subtitle="Who owes what, and for how long. Click a customer for their statement." />
      {t && (
        <div className="mb-6 grid gap-4 sm:grid-cols-3">
          <Card>
            <div className="text-sm text-stone-500">Total due</div>
            <div className="text-2xl font-semibold tabular-nums">{formatINR(t.due)}</div>
          </Card>
          <Card>
            <div className="text-sm text-stone-500">Overdue (past credit days)</div>
            <div className="text-2xl font-semibold text-red-700 tabular-nums">{formatINR(t.overdue)}</div>
          </Card>
          <Card>
            <div className="text-sm text-stone-500">Over 90 days</div>
            <div className="text-2xl font-semibold tabular-nums">{formatINR(t.b90_plus)}</div>
          </Card>
        </div>
      )}
      <Card>
        <div className="mb-3 flex flex-wrap items-center gap-3">
          <Input className="max-w-56" placeholder="Filter by area / route" value={area} onChange={(e) => setArea(e.target.value)} />
          <span className="text-sm text-stone-500">Sort:</span>
          {(
            [
              ['net', 'Amount'],
              ['overdue', 'Overdue'],
              ['oldest_days', 'Oldest bill'],
              ['party_name', 'Name'],
            ] as [SortKey, string][]
          ).map(([k, label]) => (
            <button
              key={k}
              onClick={() => setSort(k)}
              className={cx('rounded px-2 py-1 text-sm', sort === k ? 'bg-brand-50 font-medium text-brand-700' : 'text-stone-600')}
            >
              {label}
            </button>
          ))}
        </div>
        <ErrorText error={report.error} />
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-left text-stone-500">
              <tr>
                <th className="py-2">Customer</th>
                <th>Area</th>
                {COLS.map((c) => (
                  <th key={c.key} className="text-right">
                    {c.label}
                  </th>
                ))}
                <th className="text-right">Advance</th>
                <th className="text-right">Net due</th>
                <th className="text-right">Overdue</th>
                <th />
              </tr>
            </thead>
            <tbody className="divide-y divide-stone-100">
              {rows.map((r) => (
                <tr key={r.party_id} className="cursor-pointer hover:bg-stone-50" onClick={() => navigate(`/parties/${r.party_id}/ledger`)}>
                  <td className="py-2">
                    <div className="font-medium">{r.party_name}</div>
                    <div className="text-xs text-stone-500">
                      {r.phone ?? ''} · {r.open_bills} bill(s), oldest {r.oldest_days}d
                    </div>
                  </td>
                  <td>{r.area ?? '—'}</td>
                  {COLS.map((c) => (
                    <td key={c.key} className={cx('text-right tabular-nums', Number(r[c.key]) ? c.tone : 'text-stone-300')}>
                      {Number(r[c.key]) ? formatINR(String(r[c.key])) : '—'}
                    </td>
                  ))}
                  <td className="text-right tabular-nums text-green-700">{Number(r.advance) ? formatINR(r.advance) : ''}</td>
                  <td className="text-right font-semibold tabular-nums">{formatINR(r.net)}</td>
                  <td className={cx('text-right tabular-nums', Number(r.overdue) ? 'text-red-700' : 'text-stone-300')}>
                    {Number(r.overdue) ? formatINR(r.overdue) : '—'}
                  </td>
                  <td className="text-right" onClick={(e) => e.stopPropagation()}>
                    <Link to={`/receipts/new?party=${r.party_id}`}>
                      <Button variant="ghost">Collect</Button>
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
            {t && rows.length > 0 && (
              <tfoot>
                <tr className="border-t-2 border-stone-300 font-semibold">
                  <td className="py-2" colSpan={2}>
                    Total
                  </td>
                  {COLS.map((c) => (
                    <td key={c.key} className="text-right tabular-nums">
                      {formatINR(t[c.key])}
                    </td>
                  ))}
                  <td className="text-right tabular-nums">{formatINR(t.advance)}</td>
                  <td className="text-right tabular-nums">{formatINR(t.net)}</td>
                  <td className="text-right tabular-nums">{formatINR(t.overdue)}</td>
                  <td />
                </tr>
              </tfoot>
            )}
          </table>
          {rows.length === 0 && !report.isLoading && <p className="py-6 text-center text-sm text-stone-500">Nobody owes anything.</p>}
        </div>
      </Card>
    </>
  )
}
