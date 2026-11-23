import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { api } from '../api/client'
import type { SaleSummary } from '../api/types'
import { Badge, Button, Card, ErrorText, Input, PageHeader } from '../components/ui'
import { formatDate, formatINR } from '../lib/format'
import { useDebounced } from '../lib/useDebounced'

export function SalesPage() {
  const navigate = useNavigate()
  const [search, setSearch] = useState('')
  const q = useDebounced(search)
  const sales = useQuery({
    queryKey: ['sales', q],
    queryFn: () => api.get<SaleSummary[]>(`/api/sales?limit=200${q ? `&q=${encodeURIComponent(q)}` : ''}`),
  })

  return (
    <>
      <PageHeader
        title="Bills"
        subtitle="Every sales bill. Click one to print, cancel or take a return."
        actions={
          <Link to="/sales/new">
            <Button>New bill</Button>
          </Link>
        }
      />
      <Card>
        <Input
          className="mb-3 max-w-xs"
          placeholder="Search bill no. or customer"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <ErrorText error={sales.error} />
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-left text-stone-500">
              <tr>
                <th className="py-2">Bill no.</th>
                <th>Date</th>
                <th>Customer</th>
                <th>Type</th>
                <th className="text-right">Bags</th>
                <th className="text-right">Total</th>
                <th />
              </tr>
            </thead>
            <tbody className="divide-y divide-stone-100">
              {sales.data?.map((s) => (
                <tr
                  key={s.id}
                  onClick={() => navigate(`/sales/${s.id}`)}
                  className={`cursor-pointer hover:bg-stone-50 ${s.status === 'cancelled' ? 'text-stone-400' : ''}`}
                >
                  <td className="py-2 font-mono text-xs">{s.invoice_no}</td>
                  <td className="whitespace-nowrap">{formatDate(s.invoice_date)}</td>
                  <td className="font-medium">{s.customer_name}</td>
                  <td>{s.payment_mode === 'credit' ? <Badge tone="amber">Credit</Badge> : <Badge tone="green">Cash</Badge>}</td>
                  <td className="text-right tabular-nums">{s.total_bags}</td>
                  <td className={`text-right tabular-nums ${s.status === 'cancelled' ? 'line-through' : ''}`}>
                    {formatINR(s.grand_total)}
                  </td>
                  <td className="text-right">
                    {s.status === 'cancelled' && <Badge tone="red">Cancelled</Badge>}
                    {s.has_returns && <Badge>Returned</Badge>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {sales.data?.length === 0 && <p className="py-6 text-center text-sm text-stone-500">No bills found.</p>}
        </div>
      </Card>
    </>
  )
}
