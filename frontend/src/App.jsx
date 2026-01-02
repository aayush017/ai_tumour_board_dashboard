import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider, useAuth } from './contexts/AuthContext'
import Layout from './components/Layout'
import ProtectedRoute from './components/ProtectedRoute'
import PatientList from './pages/PatientList'
import PatientCreate from './pages/PatientCreate'
import PatientEdit from './pages/PatientEdit'
import PatientView from './pages/PatientView'
import MasterLogin from './pages/MasterLogin'
import MasterDashboard from './pages/MasterDashboard'
import UserLogin from './pages/UserLogin'

// Component to handle root route redirect
function RootRedirect() {
  const { isAuthenticated, loading } = useAuth()

  if (loading) {
    return (
      <div className="flex justify-center items-center min-h-screen">
        <div className="text-gray-600">Loading...</div>
      </div>
    )
  }

  // If authenticated, go to patient list; otherwise, go to login
  return isAuthenticated ? <Navigate to="/patients" replace /> : <Navigate to="/login" replace />
}

function AppRoutes() {
  return (
    <Routes>
      {/* Root redirect */}
      <Route path="/" element={<RootRedirect />} />

      {/* Public auth routes */}
      <Route path="/login" element={<UserLogin />} />
      <Route path="/master/login" element={<MasterLogin />} />

      {/* Protected patient routes */}
      <Route
        path="/patients"
        element={
          <ProtectedRoute>
            <PatientList />
          </ProtectedRoute>
        }
      />
      <Route
        path="/create"
        element={
          <ProtectedRoute>
            <PatientCreate />
          </ProtectedRoute>
        }
      />
      <Route
        path="/patient/:caseId"
        element={
          <ProtectedRoute>
            <PatientView />
          </ProtectedRoute>
        }
      />
      <Route
        path="/patient/:caseId/edit"
        element={
          <ProtectedRoute>
            <PatientEdit />
          </ProtectedRoute>
        }
      />

      {/* Protected master routes */}
      <Route
        path="/master"
        element={
          <ProtectedRoute>
            <MasterDashboard />
          </ProtectedRoute>
        }
      />
    </Routes>
  )
}

function App() {
  return (
    <Router>
      <AuthProvider>
        <Layout>
          <AppRoutes />
        </Layout>
      </AuthProvider>
    </Router>
  )
}

export default App
