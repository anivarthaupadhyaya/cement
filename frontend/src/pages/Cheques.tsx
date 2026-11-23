import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { api } from '../api/client'
import type { Receipt } from '../api/types'
import { Button, Card, ErrorText, PageHeader } from '../components/ui'
import { cx } from '../lib/cx'
import { formatDate, formatINR, todayISO } from '../lib/format'
import { ChequeBadge } from './Receipts'

const TABS = [
  ['pending', 'To deposit / clear'],
  ['bounced', 'Bounced'],
  ['cleared', 'Cleared'],
] as const

export function ChequesPage() {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [tab, setTab] = useState<(typeof TABS)[number][0]>('pending')
  const cheques = useQuery({ queryKey: ['cheques', tab], queryFn: () => api.get<Receipt[]>(`/api/cheques?status=${tab}`) })
  const act = useMutation({
    mutationFn: ({ id, action }: { id: number; action: 'deposit' | 'clear' }) =>
      api.post<Receipt>(`/api/receipts/${id}/cheque`, { action }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['cheques'] }),
  })
  const today = todayISO()

  return (
    <>
      <PageHeader title="Cheques" subtitle="Post-dated and pending cheques. Mark a bounce from the receipt page to add a charge." />
      <div className="mb-4 flex gap-2">
        {TABS.map(([k, label]) => (
          <button
            key={k}
            onClick={() => setTab(k)}
            className={cx('rounded-md px-3 py-1.5 text-sm', tab === k ? 'bg-brand-600 text-white' : 'bg-white text-stone-700 border border-stone-300')}
          >
            {label}
          </button>
        ))}
      </div>
      <Card>
        <ErrorText error={cheques.error ?? act.error} />
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-left text-stone-500">
              <tr>
                <th className="py-2">Cheque date</th>
                <th>Customer</th>
                <th>Cheque</th>
                <th>Bank</th>
                <th className="text-right">Amount</th>
                <th>Status</th>
                <th />
              </tr>
            </thead>
            <tbody className="divide-y divide-stone-100">
              {cheques.data?.map((c) => {
                const due = c.cheque_date && c.cheque_date <= today
                return (
                  <tr key={c.id} className="hover:bg-stone-50">
                    <td className={cx('py-2', tab === 'pending' && due ? 'font-semibold text-brand-700' : '')}>
                      {formatDate(c.cheque_date)}
                      {tab === 'pending' && !due && <span className="ml-1 text-xs text-stone-500">(post-dated)</span>}
                    </td>
                    <td className="cursor-pointer font-medium hover:underline" onClick={() => navigate(`/receipts/${c.id}`)}>
                      {c.party_name}
                    </td>
                    <td className="font-mono text-xs">{c.cheque_no}</td>
                    <td>{c.bank_name ?? '—'}</td>
                    <td className="text-right tabular-nums">{formatINR(c.amount)}</td>
                    <td>
                      <ChequeBadge status={c.cheque_status} />
                    </td>
                    <td className="text-right whitespace-nowrap">
                      {c.cheque_status === 'received' && (
                        <Button variant="ghost" onClick={() => act.mutate({ id: c.id, action: 'deposit' })}>
                          Deposited
                        </Button>
                      )}
                      {(c.cheque_status === 'received' || c.cheque_status === 'deposited') && (
                        <Button variant="ghost" onClick={() => act.mutate({ id: c.id, action: 'clear' })}>
                          Cleared
                        </Button>
                      )}
                      {tab === 'pending' && (
                        <Button variant="ghost" onClick={() => navigate(`/receipts/${c.id}`)}>
                          Bounced…
                        </Button>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
          {cheques.data?.length === 0 && <p className="py-6 text-center text-sm text-stone-500">No cheques here.</p>}
        </div>
      </Card>
    </>
  )
}
