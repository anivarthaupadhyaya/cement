import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { api } from '../api/client'
import type { OpenItem, Shop, Statement } from '../api/types'
import { Button, Card, ErrorText, Field, Input, PageHeader } from '../components/ui'
import { cx } from '../lib/cx'
import { formatDate, formatINR, todayISO, whatsappLink } from '../lib/format'

const KIND_LABELS: Record<string, string> = {
  opening: 'Old balance',
  invoice: 'Bill',
  invoice_cancel: 'Bill cancelled',
  credit_note: 'Goods returned',
  receipt: 'Payment',
  receipt_cancel: 'Payment cancelled',
  cheque_bounce: 'Cheque bounced',
  bounce_charge: 'Bounce charge',
}

function fyStart(): string {
  const d = new Date()
  const year = d.getMonth() >= 3 ? d.getFullYear() : d.getFullYear() - 1
  return `${year}-04-01`
}

/** "Rs 12,500 due" / "Rs 800 advance" */
function balanceText(v: string) {
  const n = Number(v)
  if (n === 0) return 'Nil'
  return n > 0 ? `${formatINR(v)} due` : `${formatINR(v.replace('-', ''))} advance`
}

export function StatementPage() {
  const { id } = useParams()
  const [range, setRange] = useState({ from: fyStart(), to: todayISO() })
  const statement = useQuery({
    queryKey: ['statement', id, range],
    queryFn: () => api.get<Statement>(`/api/parties/${id}/ledger?date_from=${range.from}&date_to=${range.to}`),
  })
  const openBills = useQuery({ queryKey: ['open-bills', id], queryFn: () => api.get<OpenItem[]>(`/api/parties/${id}/open-bills`) })
  const shop = useQuery({ queryKey: ['shop'], queryFn: () => api.get<Shop>('/api/shop') })

  const s = statement.data
  const shareText = s
    ? [
        `Namaskara ${s.party_name},`,
        `Your account with ${shop.data?.name ?? 'us'} as on ${formatDate(s.date_to)}: ${balanceText(s.closing)}.`,
        ...(openBills.data?.length
          ? ['Pending bills:', ...openBills.data.slice(0, 8).map((b) => `• ${b.ref_no} (${formatDate(b.date)}): ${formatINR(b.balance)}`)]
          : []),
        'Thank you.',
      ].join('\n')
    : ''

  return (
    <>
      <div className="print:hidden">
        <PageHeader
          title={s ? `Statement: ${s.party_name}` : 'Statement'}
          subtitle="Every bill, payment and return with the running balance."
          actions={
            <div className="flex flex-wrap gap-2">
              <Link to={`/receipts/new?party=${id}`}>
                <Button>Receive payment</Button>
              </Link>
              <Button variant="secondary" onClick={() => window.print()}>
                Print
              </Button>
              {s && (
                <a href={whatsappLink(s.phone, shareText)} target="_blank" rel="noreferrer">
                  <Button variant="secondary">Share on WhatsApp</Button>
                </a>
              )}
            </div>
          }
        />
        <div className="mb-4 flex flex-wrap items-end gap-3">
          <div className="w-44">
            <Field label="From">
              <Input type="date" value={range.from} onChange={(e) => setRange({ ...range, from: e.target.value })} />
            </Field>
          </div>
          <div className="w-44">
            <Field label="To">
              <Input type="date" value={range.to} onChange={(e) => setRange({ ...range, to: e.target.value })} />
            </Field>
          </div>
        </div>
      </div>

      <ErrorText error={statement.error} />
      {s && (
        <Card>
          <div className="mb-3 hidden text-center print:block">
            <div className="text-lg font-bold">{shop.data?.name}</div>
            <div className="text-sm">
              Statement of account: <b>{s.party_name}</b> · {formatDate(s.date_from)} to {formatDate(s.date_to)}
            </div>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-left text-stone-500">
                <tr>
                  <th className="py-2">Date</th>
                  <th>Particulars</th>
                  <th>Ref</th>
                  <th className="text-right">Debit</th>
                  <th className="text-right">Credit</th>
                  <th className="text-right">Balance</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-stone-100">
                <tr className="bg-stone-50 font-medium">
                  <td className="py-2">{formatDate(s.date_from)}</td>
                  <td colSpan={4}>Opening balance</td>
                  <td className="text-right tabular-nums">{balanceText(s.opening)}</td>
                </tr>
                {s.lines.map((l) => (
                  <tr key={l.id}>
                    <td className="py-2 whitespace-nowrap">{formatDate(l.date)}</td>
                    <td>
                      {KIND_LABELS[l.kind] ?? l.kind}
                      {l.narration && <span className="text-stone-500"> · {l.narration}</span>}
                    </td>
                    <td className="font-mono text-xs">{l.ref_no}</td>
                    <td className="text-right tabular-nums">{Number(l.debit) ? formatINR(l.debit) : ''}</td>
                    <td className="text-right tabular-nums text-green-700">{Number(l.credit) ? formatINR(l.credit) : ''}</td>
                    <td className="text-right tabular-nums">{balanceText(l.balance)}</td>
                  </tr>
                ))}
                <tr className="border-t-2 border-stone-300 font-semibold">
                  <td className="py-2" colSpan={3}>
                    Closing balance
                  </td>
                  <td className="text-right tabular-nums">{formatINR(s.total_debit)}</td>
                  <td className="text-right tabular-nums">{formatINR(s.total_credit)}</td>
                  <td className={cx('text-right tabular-nums', Number(s.closing) > 0 ? 'text-red-700' : 'text-green-700')}>
                    {balanceText(s.closing)}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          {s.lines.length === 0 && <p className="py-4 text-center text-sm text-stone-500">No entries in this period.</p>}
        </Card>
      )}
    </>
  )
}
