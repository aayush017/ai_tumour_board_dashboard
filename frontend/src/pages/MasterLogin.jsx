import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import axios from 'axios'
import { useAuth } from '../contexts/AuthContext'

const API_BASE_URL = 'http://localhost:8000'

export default function MasterLogin() {
  const [email, setEmail] = useState('aayush22011@iiitd.ac.in')
  const [password, setPassword] = useState('123456')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const navigate = useNavigate()
  const { login, isAuthenticated } = useAuth()

  // Redirect if already authenticated
  useEffect(() => {
    if (isAuthenticated) {
      navigate('/master', { replace: true })
    }
  }, [isAuthenticated, navigate])

  const handleSubmit = async (e) => {
    e.preventDefault()
    setLoading(true)
    setError(null)

    try {
      // Step 1: Authenticate with master credentials
      await axios.post(
        `${API_BASE_URL}/auth/login/master`,
        { email, password },
        { withCredentials: true }
      )

      // Step 2: Verify session was established
      const sessionResponse = await axios.get(
        `${API_BASE_URL}/auth/me`,
        { withCredentials: true }
      )

      // Step 3: Update auth context
      await login(sessionResponse.data)

      // Step 4: Redirect only after session is verified
      navigate('/master', { replace: true })
    } catch (err) {
      console.error('Master login failed', err)
      setError(
        err.response?.data?.detail || err.message || 'Login failed. Please try again.'
      )
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="max-w-md mx-auto mt-12 bg-white rounded-lg shadow p-6">
      <h1 className="text-2xl font-bold mb-4 text-gray-900">Master Login</h1>
      <p className="text-sm text-gray-600 mb-4">
        This area is restricted to the master administrator account.
      </p>
      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Email
          </label>
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Password
          </label>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
          />
        </div>
        {error && (
          <div className="text-sm text-red-600 bg-red-50 border border-red-200 rounded px-3 py-2">
            {error}
          </div>
        )}
        <button
          type="submit"
          disabled={loading}
          className="w-full mt-2 px-4 py-2 bg-blue-600 text-white rounded-md text-sm font-medium hover:bg-blue-700 disabled:opacity-50"
        >
          {loading ? 'Logging in...' : 'Login as Master'}
        </button>
      </form>
    </div>
  )
}







