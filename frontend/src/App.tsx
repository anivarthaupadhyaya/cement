import { Route, Routes } from 'react-router-dom'

import { Layout } from './components/Layout'
import { RequireAuth } from './lib/auth'
import { AuditPage } from './pages/Audit'
import { DashboardPage } from './pages/Dashboard'
import { LoginPage } from './pages/Login'
import { PartiesPage } from './pages/Parties'
import { ProductsPage } from './pages/Products'
import { PurchaseDetailPage } from './pages/PurchaseDetail'
import { PurchaseNewPage } from './pages/PurchaseNew'
import { PurchasesPage } from './pages/Purchases'
import { RatesPage } from './pages/Rates'
import { SettingsPage } from './pages/Settings'
import { StockPage } from './pages/Stock'
import { UsersPage } from './pages/Users'

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        element={
          <RequireAuth>
            <Layout />
          </RequireAuth>
        }
      >
        <Route index element={<DashboardPage />} />
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
