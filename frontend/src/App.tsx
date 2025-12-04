import { Navigate, Route, Routes } from 'react-router-dom'
import { OverviewTab } from './features/overview/OverviewTab'
import { PriorityOrdersTab } from './features/priority/PriorityOrdersTab'
import { TatOrdersTab } from './features/tat/TatOrdersTab'
import { DashboardPage } from './pages/DashboardPage'
import { LoginPage } from './pages/LoginPage'
import { ProtectedRoute } from './features/auth/ProtectedRoute'

export function App() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/dashboard" replace />} />
      <Route path="/login" element={<LoginPage />} />
      <Route
        path="/dashboard"
        element={
          <ProtectedRoute>
            <DashboardPage />
          </ProtectedRoute>
        }
      >
        <Route index element={<OverviewTab />} />
        <Route path="priority-orders" element={<PriorityOrdersTab />} />
        <Route path="tat-orders" element={<TatOrdersTab />} />
      </Route>
      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  )
}
