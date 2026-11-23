import { useQuery } from '@tanstack/react-query'
import { useEffect } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'

import { api } from '../api/client'
import type { Sale, Shop } from '../api/types'
import { formatDate, formatINR, paiseToRupees, toPaise } from '../lib/format'
import { STATES } from '../lib/states'

/** Printable tax invoice (or delivery challan without prices). Opens the print dialog itself. */
export function PrintSalePage() {
  const { id } = useParams()
  const [params] = useSearchParams()
  const challan = params.get('type') === 'challan'

  const sale = useQuery({ queryKey: ['sale', id], queryFn: () => api.get<Sale>(`/api/sales/${id}`) })
  const shop = useQuery({ queryKey: ['shop'], queryFn: () => api.get<Shop>('/api/shop') })
  const ready = sale.data && shop.data

  useEffect(() => {
    if (!ready) return
    document.title = `${challan ? 'Challan' : 'Invoice'} ${sale.data.invoice_no}`
    const t = setTimeout(() => window.print(), 300)
    return () => clearTimeout(t)
  }, [ready, challan, sale.data])

  if (!ready) return <p className="p-8 text-stone-500">Preparing…</p>
  const s = sale.data
  const sh = shop.data
  const cancelled = s.status === 'cancelled'
  const totalBags = s.lines.reduce((a, l) => a + l.qty, 0)

  return (
    <div className="mx-auto max-w-[210mm] bg-white p-8 text-[13px] text-black print:max-w-none print:p-0">
      <style>{`@page { size: A4; margin: 12mm } @media print { body { background: white } }`}</style>
      <div className="mb-4 flex justify-end gap-2 print:hidden">
        <button className="rounded border px-3 py-1" onClick={() => window.print()}>
          Print
        </button>
        <button className="rounded border px-3 py-1" onClick={() => window.close()}>
          Close
        </button>
      </div>

      <div className="relative border border-black">
        {cancelled && (
          <div className="pointer-events-none absolute inset-0 flex items-center justify-center text-7xl font-bold text-red-600/25 -rotate-12">
            CANCELLED
          </div>
        )}
        <div className="border-b border-black p-3 text-center">
          <div className="text-xs font-semibold tracking-widest">{challan ? 'DELIVERY CHALLAN' : 'TAX INVOICE'}</div>
          <div className="text-2xl font-bold">{sh.name}</div>
          <div>{sh.address}</div>
          <div>
            {sh.gstin && <>GSTIN: <b>{sh.gstin}</b> · </>}
            State: {sh.state_name} ({sh.state_code}){sh.phone && <> · Ph: {sh.phone}</>}
          </div>
        </div>

        <div className="grid grid-cols-2 border-b border-black">
          <div className="border-r border-black p-3">
            <div className="text-xs text-stone-600">Bill to</div>
            <div className="font-semibold">{s.customer_name}</div>
            {s.customer_address && <div>{s.customer_address}</div>}
            {s.customer_phone && <div>Ph: {s.customer_phone}</div>}
            {s.customer_gstin && <div>GSTIN: <b>{s.customer_gstin}</b></div>}
            <div>
              Place of supply: {STATES[s.place_of_supply] ?? s.place_of_supply} ({s.place_of_supply})
            </div>
          </div>
          <div className="p-3">
            <table className="w-full">
              <tbody>
                <tr><td className="text-stone-600">{challan ? 'Challan for bill' : 'Invoice no.'}</td><td className="font-semibold">{s.invoice_no}</td></tr>
                <tr><td className="text-stone-600">Date</td><td>{formatDate(s.invoice_date)}</td></tr>
                <tr><td className="text-stone-600">Payment</td><td>{s.payment_mode === 'credit' ? 'Credit' : 'Cash'}</td></tr>
                {s.vehicle_no && <tr><td className="text-stone-600">Vehicle</td><td>{s.vehicle_no}</td></tr>}
                {s.delivery_address && <tr><td className="text-stone-600">Deliver to</td><td>{s.delivery_address}</td></tr>}
              </tbody>
            </table>
          </div>
        </div>

        <table className="w-full border-collapse">
          <thead>
            <tr className="border-b border-black text-left">
              <th className="p-2">#</th>
              <th className="p-2">Description</th>
              <th className="p-2">HSN</th>
              <th className="p-2 text-right">Bags</th>
              {!challan && (
                <>
                  <th className="p-2 text-right">Rate (incl. GST)</th>
                  <th className="p-2 text-right">GST %</th>
                  <th className="p-2 text-right">Taxable</th>
                  <th className="p-2 text-right">Amount</th>
                </>
              )}
            </tr>
          </thead>
          <tbody>
            {s.lines.map((l, i) => (
              <tr key={l.id} className="border-b border-stone-300 align-top">
                <td className="p-2">{i + 1}</td>
                <td className="p-2">{l.product_name}</td>
                <td className="p-2">{l.hsn_code}</td>
                <td className="p-2 text-right tabular-nums">{l.qty}</td>
                {!challan && (
                  <>
                    <td className="p-2 text-right tabular-nums">{formatINR(l.rate)}</td>
                    <td className="p-2 text-right tabular-nums">{Number(l.gst_rate)}%</td>
                    <td className="p-2 text-right tabular-nums">{formatINR(l.taxable)}</td>
                    <td className="p-2 text-right tabular-nums">
                      {formatINR(paiseToRupees(toPaise(l.taxable) + toPaise(l.gst_amount)))}
                    </td>
                  </>
                )}
              </tr>
            ))}
            {!challan && Number(s.delivery_charge) > 0 && (
              <tr className="border-b border-stone-300">
                <td className="p-2" />
                <td className="p-2">Delivery charges</td>
                <td className="p-2" />
                <td className="p-2" />
                <td className="p-2" />
                <td className="p-2" />
                <td className="p-2 text-right tabular-nums">{formatINR(s.delivery_taxable)}</td>
                <td className="p-2 text-right tabular-nums">{formatINR(s.delivery_charge)}</td>
              </tr>
            )}
            <tr className="border-b border-black font-semibold">
              <td className="p-2" />
              <td className="p-2">Total</td>
              <td className="p-2" />
              <td className="p-2 text-right tabular-nums">{totalBags}</td>
              {!challan && <td colSpan={4} />}
            </tr>
          </tbody>
        </table>

        {!challan ? (
          <div className="grid grid-cols-[1fr_260px]">
            <div className="border-r border-black p-3">
              <div className="text-xs text-stone-600">Amount in words</div>
              <div className="font-semibold">{s.amount_in_words}</div>
              {sh.bank && (
                <div className="mt-3">
                  <div className="text-xs text-stone-600">Bank details</div>
                  <div>{sh.bank}</div>
                </div>
              )}
            </div>
            <table className="w-full">
              <tbody>
                <tr><td className="px-3 py-1">Taxable value</td><td className="px-3 py-1 text-right tabular-nums">{formatINR(s.taxable_total)}</td></tr>
                {s.is_interstate ? (
                  <tr><td className="px-3 py-1">IGST</td><td className="px-3 py-1 text-right tabular-nums">{formatINR(s.igst_total)}</td></tr>
                ) : (
                  <>
                    <tr><td className="px-3 py-1">CGST</td><td className="px-3 py-1 text-right tabular-nums">{formatINR(s.cgst_total)}</td></tr>
                    <tr><td className="px-3 py-1">SGST</td><td className="px-3 py-1 text-right tabular-nums">{formatINR(s.sgst_total)}</td></tr>
                  </>
                )}
                <tr><td className="px-3 py-1">Round off</td><td className="px-3 py-1 text-right tabular-nums">{formatINR(s.round_off)}</td></tr>
                <tr className="border-t border-black text-base font-bold">
                  <td className="px-3 py-2">Grand total</td>
                  <td className="px-3 py-2 text-right tabular-nums">{formatINR(s.grand_total)}</td>
                </tr>
              </tbody>
            </table>
          </div>
        ) : (
          <div className="p-3 text-stone-700">Goods sent as per the bill above. Please check the bags and sign on receipt.</div>
        )}

        <div className="grid grid-cols-2 border-t border-black">
          <div className="border-r border-black p-3 text-xs text-stone-600">
            {challan ? 'Received the above bags in good condition.' : 'Goods once sold are subject to our terms. E. & O.E.'}
            <div className="mt-10">Customer's signature</div>
          </div>
          <div className="p-3 text-right">
            <div>For {sh.name}</div>
            <div className="mt-10 text-xs text-stone-600">Authorised signatory</div>
          </div>
        </div>
      </div>
      <p className="mt-2 text-center text-[10px] text-stone-500">This is a computer-generated document.</p>
    </div>
  )
}
