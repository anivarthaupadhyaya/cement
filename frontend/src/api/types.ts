export type Role = 'owner' | 'accountant' | 'billing' | 'godown'

export interface User {
  id: number
  username: string
  full_name: string
  role: Role
  is_active: boolean
}

export interface AuditEntry {
  id: number
  table_name: string
  record_id: string | null
  action: 'INSERT' | 'UPDATE' | 'DELETE'
  user_id: number | null
  old_data: Record<string, unknown> | null
  new_data: Record<string, unknown> | null
  changed_at: string
}

export const ROLE_LABELS: Record<Role, string> = {
  owner: 'Owner',
  accountant: 'Accountant',
  billing: 'Billing clerk',
  godown: 'Godown keeper',
}

// ---- Masters ---------------------------------------------------------------
// Money and quantities arrive as exact decimal strings (e.g. "380.00"), never floats.
export type Decimal = string

export interface Brand {
  id: number
  name: string
  is_active: boolean
}

export interface Product {
  id: number
  brand_id: number
  brand_name: string
  name: string
  grade: string
  bag_kg: Decimal
  hsn_code: string
  reorder_level: number
  is_active: boolean
}

export interface Godown {
  id: number
  name: string
  address: string | null
  is_active: boolean
}

export type PartyKind = 'customer' | 'supplier' | 'both'

export interface Party {
  id: number
  kind: PartyKind
  name: string
  phone: string | null
  gstin: string | null
  state_code: string
  address: string | null
  area: string | null
  credit_limit: Decimal
  credit_days: number
  notes: string | null
  is_active: boolean
}

export interface GstRate {
  id: number
  hsn_code: string
  rate: Decimal
  effective_from: string
}

export interface RateCardRow {
  product_id: number
  product_name: string
  hsn_code: string
  gst_rate: Decimal | null
  rate: Decimal | null
  effective_from: string | null
  previous_rate: Decimal | null
}

export const CEMENT_GRADES = ['OPC 43', 'OPC 53', 'PPC', 'PSC', 'PCC']

// ---- Purchases & stock -------------------------------------------------------
export interface PurchaseSummary {
  id: number
  supplier_id: number
  supplier_name: string
  supplier_invoice_no: string
  invoice_date: string
  received_date: string
  godown_name: string
  total_bags: number
  invoice_total: Decimal
  status: 'active' | 'cancelled'
}

export interface PurchaseLine {
  id: number
  product_id: number
  product_name: string
  qty_invoiced: number
  qty_received: number
  qty_damaged: number
  qty_short: number
  rate: Decimal
  gst_rate: Decimal
  taxable: Decimal
  gst_amount: Decimal
  charges: Decimal
  landed_cost: Decimal
}

export interface Purchase extends PurchaseSummary {
  godown_id: number
  vehicle_no: string | null
  lr_no: string | null
  is_interstate: boolean
  freight: Decimal
  unloading: Decimal
  other_charges: Decimal
  taxable_total: Decimal
  cgst_total: Decimal
  sgst_total: Decimal
  igst_total: Decimal
  round_off: Decimal
  notes: string | null
  cancel_reason: string | null
  created_at: string
  lines: PurchaseLine[]
}

export interface StockRow {
  product_id: number
  product_name: string
  godown_id: number
  godown_name: string
  qty: number
  reorder_level: number
  low: boolean
  avg_cost: Decimal | null
  value: Decimal | null
}

export interface Movement {
  id: number
  movement_date: string
  product_name: string
  godown_name: string
  qty: number
  kind: string
  ref_type: string | null
  ref_id: number | null
  note: string | null
  unit_cost: Decimal | null
  created_at: string
}

export const MOVEMENT_LABELS: Record<string, string> = {
  opening: 'Opening stock',
  purchase: 'Purchase',
  purchase_cancel: 'Purchase cancelled',
  sale: 'Sale',
  sale_return: 'Sale return',
  sale_cancel: 'Sale cancelled',
  damage: 'Damage',
  adjustment: 'Adjustment',
}
