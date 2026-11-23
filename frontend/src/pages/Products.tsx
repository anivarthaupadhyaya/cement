import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

import { api } from '../api/client'
import type { Brand, Product } from '../api/types'
import { CEMENT_GRADES } from '../api/types'
import { Badge, Button, Card, ErrorText, Field, Input, PageHeader, Select } from '../components/ui'
import { useMe } from '../lib/auth'
import { can } from '../lib/roles'

export function ProductsPage() {
  const qc = useQueryClient()
  const { data: me } = useMe()
  const canEdit = can(me, 'owner', 'accountant')

  const brands = useQuery({ queryKey: ['brands'], queryFn: () => api.get<Brand[]>('/api/brands') })
  const products = useQuery({ queryKey: ['products'], queryFn: () => api.get<Product[]>('/api/products') })
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ['brands'] })
    qc.invalidateQueries({ queryKey: ['products'] })
    qc.invalidateQueries({ queryKey: ['rate-card'] })
  }

  const [brandName, setBrandName] = useState('')
  const addBrand = useMutation({
    mutationFn: () => api.post<Brand>('/api/brands', { name: brandName }),
    onSuccess: () => {
      setBrandName('')
      refresh()
    },
  })

  const [form, setForm] = useState({ brand_id: '', grade: 'PPC', bag_kg: '50', reorder_level: '0' })
  const addProduct = useMutation({
    mutationFn: () =>
      api.post<Product>('/api/products', {
        brand_id: Number(form.brand_id),
        grade: form.grade.trim(),
        bag_kg: form.bag_kg,
        reorder_level: Number(form.reorder_level || 0),
      }),
    onSuccess: () => {
      setForm((f) => ({ ...f, grade: 'PPC' }))
      refresh()
    },
  })

  const toggle = useMutation({
    mutationFn: (p: Product) => api.patch<Product>(`/api/products/${p.id}`, { is_active: !p.is_active }),
    onSuccess: refresh,
  })

  const activeBrands = brands.data?.filter((b) => b.is_active) ?? []

  return (
    <>
      <PageHeader title="Products" subtitle="Brands and the cement grades you stock. Stock and rates are per bag." />
      <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
        <Card>
          <ErrorText error={products.error ?? toggle.error} />
          {products.data?.length === 0 && (
            <p className="py-6 text-center text-sm text-stone-500">No products yet. Add a brand, then its grades.</p>
          )}
          <table className="w-full text-sm">
            <thead className="text-left text-stone-500">
              <tr>
                <th className="py-2">Product</th>
                <th>Grade</th>
                <th className="text-right">Bag</th>
                <th>HSN</th>
                <th className="text-right">Reorder at</th>
                <th>Status</th>
                {canEdit && <th />}
              </tr>
            </thead>
            <tbody className="divide-y divide-stone-100">
              {products.data?.map((p) => (
                <tr key={p.id} className={p.is_active ? '' : 'text-stone-400'}>
                  <td className="py-2 font-medium">{p.brand_name}</td>
                  <td>{p.grade}</td>
                  <td className="text-right tabular-nums">{Number(p.bag_kg)} kg</td>
                  <td>{p.hsn_code}</td>
                  <td className="text-right tabular-nums">{p.reorder_level} bags</td>
                  <td>{p.is_active ? <Badge tone="green">Active</Badge> : <Badge>Hidden</Badge>}</td>
                  {canEdit && (
                    <td className="text-right">
                      <Button variant="ghost" onClick={() => toggle.mutate(p)}>
                        {p.is_active ? 'Hide' : 'Show'}
                      </Button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </Card>

        {canEdit && (
          <div className="space-y-6">
            <Card title="Add product">
              <form
                className="space-y-3"
                onSubmit={(e) => {
                  e.preventDefault()
                  addProduct.mutate()
                }}
              >
                <Field label="Brand">
                  <Select
                    required
                    value={form.brand_id}
                    onChange={(e) => setForm({ ...form, brand_id: e.target.value })}
                  >
                    <option value="">Choose…</option>
                    {activeBrands.map((b) => (
                      <option key={b.id} value={b.id}>
                        {b.name}
                      </option>
                    ))}
                  </Select>
                </Field>
                <Field label="Grade">
                  <Input
                    required
                    list="grades"
                    value={form.grade}
                    onChange={(e) => setForm({ ...form, grade: e.target.value })}
                  />
                  <datalist id="grades">
                    {CEMENT_GRADES.map((g) => (
                      <option key={g} value={g} />
                    ))}
                  </datalist>
                </Field>
                <div className="grid grid-cols-2 gap-3">
                  <Field label="Bag (kg)">
                    <Input
                      required
                      inputMode="decimal"
                      value={form.bag_kg}
                      onChange={(e) => setForm({ ...form, bag_kg: e.target.value })}
                    />
                  </Field>
                  <Field label="Reorder at (bags)">
                    <Input
                      inputMode="numeric"
                      value={form.reorder_level}
                      onChange={(e) => setForm({ ...form, reorder_level: e.target.value })}
                    />
                  </Field>
                </div>
                <ErrorText error={addProduct.error} />
                <Button type="submit" className="w-full" disabled={addProduct.isPending}>
                  Add product
                </Button>
              </form>
            </Card>

            <Card title="Brands">
              <ul className="mb-3 flex flex-wrap gap-2">
                {brands.data?.map((b) => (
                  <li key={b.id}>
                    <Badge tone={b.is_active ? 'amber' : 'stone'}>{b.name}</Badge>
                  </li>
                ))}
              </ul>
              <form
                className="flex gap-2"
                onSubmit={(e) => {
                  e.preventDefault()
                  addBrand.mutate()
                }}
              >
                <Input
                  placeholder="e.g. UltraTech"
                  value={brandName}
                  onChange={(e) => setBrandName(e.target.value)}
                  required
                />
                <Button type="submit" variant="secondary" disabled={addBrand.isPending}>
                  Add
                </Button>
              </form>
              <div className="mt-2">
                <ErrorText error={addBrand.error} />
              </div>
            </Card>
          </div>
        )}
      </div>
    </>
  )
}
