import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'

import { api } from '../api/client'
import type { Party } from '../api/types'
import { formatINR } from '../lib/format'
import { useDebounced } from '../lib/useDebounced'
import { cx } from '../lib/cx'
import { Input } from './ui'

/** Type-ahead customer search. Arrow keys + Enter pick; Esc clears. */
export function CustomerPicker({
  value,
  onChange,
  autoFocus,
}: {
  value: Party | null
  onChange: (p: Party | null) => void
  autoFocus?: boolean
}) {
  const [text, setText] = useState('')
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(0)
  const q = useDebounced(text, 150)

  const results = useQuery({
    queryKey: ['parties', 'pick', q],
    queryFn: () => api.get<Party[]>(`/api/parties?kind=customer&active=true&limit=8&q=${encodeURIComponent(q)}`),
    enabled: open && q.trim().length > 0,
  })
  const items = results.data ?? []

  if (value) {
    return (
      <div className="flex items-center justify-between rounded-md border border-brand-500 bg-brand-50 px-3 py-2">
        <div>
          <div className="font-medium">{value.name}</div>
          <div className="text-xs text-stone-600">
            {[value.phone, value.gstin, value.area].filter(Boolean).join(' · ') || 'No details'}
            {Number(value.credit_limit) > 0 && ` · Credit ${formatINR(value.credit_limit)} / ${value.credit_days} days`}
          </div>
        </div>
        <button
          type="button"
          className="text-sm text-brand-700 hover:underline"
          onClick={() => {
            onChange(null)
            setText('')
          }}
        >
          Change
        </button>
      </div>
    )
  }

  const pick = (p: Party) => {
    onChange(p)
    setOpen(false)
    setText('')
  }

  return (
    <div className="relative">
      <Input
        autoFocus={autoFocus}
        placeholder="Search customer by name or phone… (leave empty for walk-in)"
        value={text}
        onChange={(e) => {
          setText(e.target.value)
          setOpen(true)
          setActive(0)
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
        onKeyDown={(e) => {
          if (e.key === 'ArrowDown') {
            e.preventDefault()
            setActive((a) => Math.min(a + 1, items.length - 1))
          } else if (e.key === 'ArrowUp') {
            e.preventDefault()
            setActive((a) => Math.max(a - 1, 0))
          } else if (e.key === 'Enter' && open && items[active]) {
            e.preventDefault()
            pick(items[active])
          } else if (e.key === 'Escape') {
            setText('')
            setOpen(false)
          }
        }}
      />
      {open && items.length > 0 && (
        <ul className="absolute z-10 mt-1 w-full overflow-hidden rounded-md border border-stone-200 bg-white shadow-lg">
          {items.map((p, i) => (
            <li
              key={p.id}
              onMouseDown={() => pick(p)}
              className={cx('cursor-pointer px-3 py-2 text-sm', i === active && 'bg-brand-50')}
            >
              <span className="font-medium">{p.name}</span>
              <span className="text-stone-500"> {[p.phone, p.area].filter(Boolean).join(' · ')}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
