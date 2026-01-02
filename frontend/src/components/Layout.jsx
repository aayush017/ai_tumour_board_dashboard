import { Link, useLocation, useNavigate } from 'react-router-dom'
import { Activity, Users, Plus, Database, Shield, LogOut, User } from 'lucide-react'
import { useAuth } from '../contexts/AuthContext'

export default function Layout({ children }) {
  const location = useLocation()
  const navigate = useNavigate()
  const { isAuthenticated, user, logout } = useAuth()

  const handleLogout = async () => {
    await logout()
    navigate('/login', { replace: true })
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <nav className="bg-blue-600 text-white shadow-lg">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between h-16">
            <div className="flex items-center">
              <Database className="h-8 w-8 mr-2" />
              <span className="text-xl font-bold">AI TUMOUR BOARD DASHBOARD</span>
            </div>
            <div className="flex items-center space-x-4">
              {isAuthenticated ? (
                <>
                  <Link
                    to="/patients"
                    className={`flex items-center px-3 py-2 rounded-md ${
                      location.pathname === '/patients' || location.pathname === '/'
                        ? 'bg-blue-700'
                        : 'hover:bg-blue-700'
                    }`}
                  >
                    <Users className="h-5 w-5 mr-2" />
                    All Patients
                  </Link>
                  <Link
                    to="/create"
                    className={`flex items-center px-3 py-2 rounded-md ${
                      location.pathname === '/create'
                        ? 'bg-blue-700'
                        : 'hover:bg-blue-700'
                    }`}
                  >
                    <Plus className="h-5 w-5 mr-2" />
                    New Patient
                  </Link>
                  {user?.role === 'master' && (
                    <Link
                      to="/master"
                      className={`flex items-center px-3 py-2 rounded-md ${
                        location.pathname === '/master'
                          ? 'bg-blue-700'
                          : 'hover:bg-blue-700'
                      }`}
                    >
                      <Shield className="h-5 w-5 mr-2" />
                      Master Dashboard
                    </Link>
                  )}
                  <div className="flex items-center space-x-2 border-l border-blue-500 pl-4 ml-2">
                    {user?.email && (
                      <span className="text-sm flex items-center">
                        <User className="h-4 w-4 mr-1" />
                        {user.email}
                      </span>
                    )}
                    <button
                      onClick={handleLogout}
                      className="flex items-center px-3 py-2 rounded-md hover:bg-blue-700"
                      title="Logout"
                    >
                      <LogOut className="h-5 w-5" />
                    </button>
                  </div>
                </>
              ) : (
                <>
                  <Link
                    to="/login"
                    className={`flex items-center px-3 py-2 rounded-md ${
                      location.pathname === '/login'
                        ? 'bg-blue-700'
                        : 'hover:bg-blue-700'
                    }`}
                  >
                    User Login
                  </Link>
                  <Link
                    to="/master/login"
                    className={`flex items-center px-3 py-2 rounded-md ${
                      location.pathname === '/master/login'
                        ? 'bg-blue-700'
                        : 'hover:bg-blue-700'
                    }`}
                  >
                    <Shield className="h-5 w-5 mr-2" />
                    Master Login
                  </Link>
                </>
              )}
            </div>
          </div>
        </div>
      </nav>
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {children}
      </main>
    </div>
  )
}
