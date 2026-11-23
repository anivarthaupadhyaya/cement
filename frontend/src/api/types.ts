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

// ---- Sales ---------------------------------------------------------------------
export interface PreviewLine {
  product_id: number
  product_name: string
  qty: number
  rate: Decimal
  gst_rate: Decimal
  gross: Decimal
  taxable: Decimal
  gst_amount: Decimal
  available: number
  cost_per_bag: Decimal | null
  margin: Decimal | null
  below_cost: boolean
}

export interface BillPreview {
  customer_name: string
  place_of_supply: string
  is_interstate: boolean
  lines: PreviewLine[]
  delivery_taxable: Decimal
  delivery_gst: Decimal
  taxable_total: Decimal
  cgst_total: Decimal
  sgst_total: Decimal
  igst_total: Decimal
  round_off: Decimal
  grand_total: Decimal
  total_bags: number
  outstanding: Decimal | null
  credit_limit: Decimal | null
  over_limit: boolean
  margin: Decimal | null
  warnings: string[]
}

export interface SaleSummary {
  id: number
  invoice_no: string
  invoice_date: string
  customer_name: string
  party_id: number | null
  payment_mode: 'cash' | 'credit'
  total_bags: number
  grand_total: Decimal
  status: 'active' | 'cancelled'
  has_returns: boolean
}

export interface SaleLine {
  id: number
  product_id: number
  product_name: string
  hsn_code: string
  qty: number
  qty_returned: number
  rate: Decimal
  gst_rate: Decimal
  taxable: Decimal
  gst_amount: Decimal
  cost_per_bag: Decimal | null
}

export interface SaleReturn {
  id: number
  return_no: string
  return_date: string
  reason: string
  taxable_total: Decimal
  cgst_total: Decimal
  sgst_total: Decimal
  igst_total: Decimal
  round_off: Decimal
  total: Decimal
  lines: { sales_line_id: number; product_name: string; qty: number; taxable: Decimal; gst_amount: Decimal }[]
}

export interface Sale extends SaleSummary {
  customer_phone: string | null
  customer_gstin: string | null
  customer_address: string | null
  place_of_supply: string
  is_interstate: boolean
  godown_id: number
  godown_name: string
  vehicle_no: string | null
  delivery_address: string | null
  delivery_charge: Decimal
  delivery_taxable: Decimal
  delivery_gst: Decimal
  taxable_total: Decimal
  cgst_total: Decimal
  sgst_total: Decimal
  igst_total: Decimal
  round_off: Decimal
  amount_in_words: string
  paid: Decimal
  balance_due: Decimal
  cost_total: Decimal | null
  margin: Decimal | null
  credit_override_reason: string | null
  notes: string | null
  cancel_reason: string | null
  cancelled_at: string | null
  created_at: string
  lines: SaleLine[]
  returns: SaleReturn[]
}

export interface Shop {
  name: string
  address: string
  gstin: string
  phone: string
  bank: string
  state_code: string
  state_name: string
}

export interface Quote {
  product_id: number
  party_id: number | null
  rate: Decimal
  source: 'party' | 'list'
  effective_from: string
  gst_rate: Decimal
}

// ---- Receipts & credit ---------------------------------------------------------------
export type PayMode = 'cash' | 'upi' | 'bank' | 'cheque'
export type ChequeStatus = 'received' | 'deposited' | 'cleared' | 'bounced'

export interface OpenItem {
  kind: 'invoice' | 'due'
  id: number
  ref_no: string
  date: string
  age_days: number
  amount: Decimal
  paid: Decimal
  balance: Decimal
}

export interface ReceiptPreview {
  outstanding: Decimal
  open_items: OpenItem[]
  plan: { kind: 'invoice' | 'due'; id: number; ref_no: string; amount: Decimal }[]
  advance_after: Decimal
  bounced_cheques: number
}

export interface Receipt {
  id: number
  receipt_no: string
  receipt_date: string
  party_id: number
  party_name: string
  mode: PayMode
  amount: Decimal
  reference: string | null
  cheque_no: string | null
  cheque_date: string | null
  bank_name: string | null
  cheque_status: ChequeStatus | null
  status: 'active' | 'cancelled'
  cancel_reason: string | null
  notes: string | null
  allocated: Decimal
  unallocated: Decimal
  allocations: { kind: 'invoice' | 'due'; id: number; ref_no: string; amount: Decimal }[]
  balance_after: Decimal
  amount_in_words: string
  created_at: string
}

export interface StatementLine {
  id: number
  date: string
  kind: string
  ref_no: string | null
  narration: string | null
  debit: Decimal
  credit: Decimal
  balance: Decimal
}

export interface Statement {
  party_id: number
  party_name: string
  phone: string | null
  date_from: string
  date_to: string
  opening: Decimal
  lines: StatementLine[]
  closing: Decimal
  total_debit: Decimal
  total_credit: Decimal
}

export interface AgeingRow {
  party_id: number
  party_name: string
  phone: string | null
  area: string | null
  credit_limit: Decimal
  credit_days: number
  b0_30: Decimal
  b31_60: Decimal
  b61_90: Decimal
  b90_plus: Decimal
  due: Decimal
  advance: Decimal
  net: Decimal
  overdue: Decimal
  oldest_days: number
  open_bills: number
}

export interface Ageing {
  as_of: string
  rows: AgeingRow[]
  totals: Record<string, Decimal>
}

export const PAY_MODE_LABELS: Record<PayMode, string> = {
  cash: 'Cash',
  upi: 'UPI',
  bank: 'Bank transfer',
  cheque: 'Cheque',
}
