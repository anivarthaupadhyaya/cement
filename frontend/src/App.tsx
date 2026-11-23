import { Route, Routes } from 'react-router-dom'

import { Layout } from './components/Layout'
import { RequireAuth } from './lib/auth'
import { AuditPage } from './pages/Audit'
import { ChequesPage } from './pages/Cheques'
import { DashboardPage } from './pages/Dashboard'
import { LoginPage } from './pages/Login'
import { NewBillPage } from './pages/NewBill'
import { OutstandingPage } from './pages/Outstanding'
import { PartiesPage } from './pages/Parties'
import { PrintSalePage } from './pages/PrintSale'
import { ProductsPage } from './pages/Products'
import { PurchaseDetailPage } from './pages/PurchaseDetail'
import { PurchaseNewPage } from './pages/PurchaseNew'
import { PurchasesPage } from './pages/Purchases'
import { RatesPage } from './pages/Rates'
import { ReceivePaymentPage } from './pages/ReceivePayment'
import { ReceiptDetailPage, ReceiptsPage } from './pages/Receipts'
import { SaleDetailPage } from './pages/SaleDetail'
import { SalesPage } from './pages/Sales'
import { SettingsPage } from './pages/Settings'
import { StatementPage } from './pages/Statement'
import { StockPage } from './pages/Stock'
import { UsersPage } from './pages/Users'

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        path="/sales/:id/print"
        element={
          <RequireAuth>
            <PrintSalePage />
          </RequireAuth>
        }
      />
      <Route
        element={
          <RequireAuth>
            <Layout />
          </RequireAuth>
        }
      >
        <Route index element={<DashboardPage />} />
        <Route
          path="sales/new"
          element={
            <RequireAuth roles={['owner', 'accountant', 'billing']}>
              <NewBillPage />
            </RequireAuth>
          }
        />
        <Route path="sales" element={<SalesPage />} />
        <Route
          path="receipts/new"
          element={
            <RequireAuth roles={['owner', 'accountant', 'billing']}>
              <ReceivePaymentPage />
            </RequireAuth>
          }
        />
        <Route path="receipts" element={<ReceiptsPage />} />
        <Route path="receipts/:id" element={<ReceiptDetailPage />} />
        <Route path="outstanding" element={<OutstandingPage />} />
        <Route path="parties/:id/ledger" element={<StatementPage />} />
        <Route
          path="cheques"
          element={
            <RequireAuth roles={['owner', 'accountant']}>
              <ChequesPage />
            </RequireAuth>
          }
        />
        <Route path="sales/:id" element={<SaleDetailPage />} />
        <Route path="rates" element={<RatesPage />} />
        <Route path="stock" element={<StockPage />} />
        <Route
          path="purchases"
          element={
            <RequireAuth roles={['owner', 'accountant', 'godown']}>
              <PurchasesPage />
            </RequireAuth>
          }
        />
        <Route
          path="purchases/new"
          element={
            <RequireAuth roles={['owner', 'accountant', 'godown']}>
              <PurchaseNewPage />
            </RequireAuth>
          }
        />
        <Route
          path="purchases/:id"
          element={
            <RequireAuth roles={['owner', 'accountant', 'godown']}>
              <PurchaseDetailPage />
            </RequireAuth>
          }
        />
        <Route path="parties" element={<PartiesPage />} />
        <Route path="products" element={<ProductsPage />} />
        <Route path="settings" element={<SettingsPage />} />
        <Route
          path="admin/users"
          element={
            <RequireAuth roles={['owner']}>
              <UsersPage />
            </RequireAuth>
          }
        />
        <Route
          path="admin/audit"
          element={
            <RequireAuth roles={['owner']}>
              <AuditPage />
            </RequireAuth>
          }
        />
      </Route>
    </Routes>
  )
}
