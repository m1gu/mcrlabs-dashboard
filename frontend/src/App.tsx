import { Navigate, Route, Routes } from 'react-router-dom'
import { DashboardGlimsPage } from './pages/DashboardGlimsPage'
import { LoginPage } from './pages/LoginPage'
import { ProtectedRoute } from './features/auth/ProtectedRoute'
import { GlimsOverviewTab } from './features/glimsOverview/GlimsOverviewTab'
import { PrioritySamplesTab } from './features/prioritySamples/PrioritySamplesTab'
import { GlimsTatSamplesTab } from './features/glimsTat/GlimsTatSamplesTab'

export function App() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/glims" replace />} />
      <Route path="/login" element={<LoginPage />} />
      <Route
        path="/glims"
        element={
          <ProtectedRoute>
            <DashboardGlimsPage />
          </ProtectedRoute>
        }
      >
        <Route index element={<Navigate to="overview" replace />} />
        <Route path="overview" element={<GlimsOverviewTab />} />
        <Route path="priority" element={<PrioritySamplesTab />} />
        <Route path="tat-samples" element={<GlimsTatSamplesTab />} />
      </Route>
      {/* Compat: old absolute paths pointing to /dashboard-glims/... */}
      <Route path="/dashboard-glims" element={<Navigate to="/glims" replace />} />
      <Route path="/dashboard-glims/overview" element={<Navigate to="/glims/overview" replace />} />
      <Route path="/dashboard-glims/priority" element={<Navigate to="/glims/priority" replace />} />
      <Route path="/dashboard-glims/tat-samples" element={<Navigate to="/glims/tat-samples" replace />} />
      <Route path="*" element={<Navigate to="/glims" replace />} />
    </Routes>
  )
}
