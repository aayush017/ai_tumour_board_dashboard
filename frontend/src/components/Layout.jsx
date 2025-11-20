import { Link, useLocation } from 'react-router-dom'
import { Activity, Users, Plus, Database } from 'lucide-react'

export default function Layout({ children }) {
  const location = useLocation()

  return (
    <div className="min-h-screen bg-gray-50">
      <nav className="bg-blue-600 text-white shadow-lg">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between h-16">
            <div className="flex items-center">
              <Database className="h-8 w-8 mr-2" />
              <span className="text-xl font-bold">Patient Entity Manager</span>
            </div>
            <div className="flex items-center space-x-4">
              <Link
                to="/"
                className={`flex items-center px-3 py-2 rounded-md ${
                  location.pathname === '/'
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
