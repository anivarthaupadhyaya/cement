const inr = new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 2 })

/** Display only. Values stay as decimal strings everywhere else; never do money maths in floats. */
export function formatINR(value: string | null | undefined): string {
  if (value === null || value === undefined || value === '') return '—'
  return inr.format(Number(value))
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return '—'
  return new Date(iso + (iso.length === 10 ? 'T00:00:00' : '')).toLocaleDateString('en-IN', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
  })
}

export function todayISO(): string {
  const d = new Date()
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

/** Parse a rupee string into integer paise (display-side estimates only). */
export function toPaise(value: string): number {
  const v = value.trim()
  if (!/^\d+(\.\d{0,2})?$/.test(v)) return NaN
  const [whole, frac = ''] = v.split('.')
  return Number(whole) * 100 + Number(frac.padEnd(2, '0'))
}

export function paiseToRupees(paise: number): string {
  return (paise / 100).toFixed(2)
}
