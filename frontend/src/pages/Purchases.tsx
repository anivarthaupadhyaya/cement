import { useQuery } from '@tanstack/react-query'
import { Link, useNavigate } from 'react-router-dom'

import { api } from '../api/client'
import type { PurchaseSummary } from '../api/types'
import { Badge, Button, Card, ErrorText, PageHeader } from '../components/ui'
import { formatDate, formatINR } from '../lib/format'

export function PurchasesPage() {
  const navigate = useNavigate()
  const purchases = useQuery({
    queryKey: ['purchases'],
    queryFn: () => api.get<PurchaseSummary[]>('/api/purchases?limit=200'),
  })

  return (
    <>
      <PageHeader
        title="Purchases"
        subtitle="Supplier bills and the bags received against them."
        actions={
          <Link to="/purchases/new">
            <Button>New purchase</Button>
          </Link>
        }
      />
      <Card>
        <ErrorText error={purchases.error} />
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-left text-stone-500">
              <tr>
                <th className="py-2">Bill date</th>
                <th>Supplier</th>
                <th>Bill no.</th>
                <th>Godown</th>
                <th className="text-right">Bags</th>
                <th className="text-right">Bill total</th>
                <th />
              </tr>
            </thead>
            <tbody className="divide-y divide-stone-100">
              {purchases.data?.map((p) => (
                <tr
                  key={p.id}
                  onClick={() => navigate(`/purchases/${p.id}`)}
                  className={`cursor-pointer hover:bg-stone-50 ${p.status === 'cancelled' ? 'text-stone-400 line-through' : ''}`}
                >
                  <td className="py-2 whitespace-nowrap">{formatDate(p.invoice_date)}</td>
                  <td className="font-medium">{p.supplier_name}</td>
                  <td className="font-mono text-xs">{p.supplier_invoice_no}</td>
                  <td>{p.godown_name}</td>
                  <td className="text-right tabular-nums">{p.total_bags}</td>
                  <td className="text-right tabular-nums">{formatINR(p.invoice_total)}</td>
                  <td className="text-right no-underline">
                    {p.status === 'cancelled' && <Badge tone="red">Cancelled</Badge>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {purchases.data?.length === 0 && (
            <p className="py-6 text-center text-sm text-stone-500">No purchases yet.</p>
          )}
        </div>
      </Card>
    </>
  )
}
