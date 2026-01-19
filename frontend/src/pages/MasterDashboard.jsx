import { useEffect, useState } from 'react'
import axios from 'axios'
import { useNavigate } from 'react-router-dom'

const API_BASE_URL = 'http://localhost:8000'

export default function MasterDashboard() {
  const [me, setMe] = useState(null)
  const [allowList, setAllowList] = useState([])
  const [logs, setLogs] = useState([])
  const [newEmail, setNewEmail] = useState('')
  const [pwForm, setPwForm] = useState({ current_password: '', new_password: '' })
  const [error, setError] = useState(null)
  const [savingPw, setSavingPw] = useState(false)
  const [savingEmail, setSavingEmail] = useState(false)
  const [loading, setLoading] = useState(true)

  const navigate = useNavigate()

  useEffect(() => {
    const load = async () => {
      try {
        setError(null)
        const meRes = await axios.get(`${API_BASE_URL}/auth/me`, { withCredentials: true })
        if (meRes.data.role !== 'master') {
          setError('Access denied: master role required.')
          setLoading(false)
          return
        }
        setMe(meRes.data)

        const [allowRes, logsRes] = await Promise.all([
          axios.get(`${API_BASE_URL}/admin/allow-list`, { withCredentials: true }),
          axios.get(`${API_BASE_URL}/admin/audit-logs?limit=100`, { withCredentials: true }),
        ])
        setAllowList(allowRes.data || [])
        setLogs(logsRes.data || [])
      } catch (err) {
        console.error('Failed to load master dashboard', err)
        setError(
          err.response?.data?.detail || err.message || 'Failed to load master dashboard'
        )
      } finally {
        setLoading(false)
      }
    }

    load()
  }, [])

  const handleLogout = async () => {
    try {
      await axios.post(`${API_BASE_URL}/auth/logout`, {}, { withCredentials: true })
    } catch (err) {
      console.error('Logout failed', err)
    } finally {
      navigate('/master/login')
    }
  }

  const handleAddEmail = async (e) => {
    e.preventDefault()
    if (!newEmail.trim()) return
    setSavingEmail(true)
    setError(null)
    try {
      const res = await axios.post(
        `${API_BASE_URL}/admin/allow-list`,
        { email: newEmail.trim() },
        { withCredentials: true }
      )
      setAllowList((prev) => [res.data, ...prev])
      setNewEmail('')
    } catch (err) {
      console.error('Failed to add allow-list entry', err)
      setError(
        err.response?.data?.detail ||
          err.message ||
          'Failed to add allow-list entry'
      )
    } finally {
      setSavingEmail(false)
    }
  }

  const handleRemoveEmail = async (id) => {
    if (!window.confirm('Remove this email from allow-list?')) return
    try {
      await axios.delete(`${API_BASE_URL}/admin/allow-list/${id}`, {
        withCredentials: true,
      })
      setAllowList((prev) => prev.filter((e) => e.id !== id))
    } catch (err) {
      console.error('Failed to remove allow-list entry', err)
      setError(
        err.response?.data?.detail ||
          err.message ||
          'Failed to remove allow-list entry'
      )
    }
  }

  const handleChangePassword = async (e) => {
    e.preventDefault()
    if (!pwForm.current_password || !pwForm.new_password) return
    setSavingPw(true)
    setError(null)
    try {
      await axios.post(
        `${API_BASE_URL}/admin/change-password`,
        pwForm,
        { withCredentials: true }
      )
      setPwForm({ current_password: '', new_password: '' })
      alert('Password updated successfully.')
    } catch (err) {
      console.error('Failed to change password', err)
      setError(
        err.response?.data?.detail ||
          err.message ||
          'Failed to change password'
      )
    } finally {
      setSavingPw(false)
    }
  }

  if (loading) {
    return <div className="flex justify-center py-12">Loading master dashboard...</div>
  }

  if (error && !me) {
    return (
      <div className="max-w-md mx-auto mt-12 bg-white rounded-lg shadow p-6">
        <h1 className="text-xl font-bold mb-3 text-gray-900">Master Dashboard</h1>
        <p className="text-sm text-red-600 mb-4">{error}</p>
        <button
          type="button"
          onClick={() => navigate('/master/login')}
          className="px-4 py-2 bg-blue-600 text-white rounded-md text-sm font-medium"
        >
          Go to Master Login
        </button>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Master Dashboard</h1>
          <p className="text-sm text-gray-600">
            Logged in as <span className="font-mono">{me?.email}</span> ({me?.role})
          </p>
        </div>
        <button
          type="button"
          onClick={handleLogout}
          className="px-4 py-2 bg-gray-100 text-gray-800 rounded-md text-sm font-medium hover:bg-gray-200"
        >
          Logout
        </button>
      </div>

      {error && (
        <div className="rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      )}

      {/* Change password */}
      <div className="bg-white rounded-lg shadow p-4">
        <h2 className="text-lg font-semibold mb-3">Change Master Password</h2>
        <form onSubmit={handleChangePassword} className="space-y-3 max-w-md">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Current Password
            </label>
            <input
              type="password"
              value={pwForm.current_password}
              onChange={(e) =>
                setPwForm((prev) => ({ ...prev, current_password: e.target.value }))
              }
              className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              New Password
            </label>
            <input
              type="password"
              value={pwForm.new_password}
              onChange={(e) =>
                setPwForm((prev) => ({ ...prev, new_password: e.target.value }))
              }
              className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            />
          </div>
          <button
            type="submit"
            disabled={savingPw}
            className="px-4 py-2 bg-blue-600 text-white rounded-md text-sm font-medium hover:bg-blue-700 disabled:opacity-50"
          >
            {savingPw ? 'Saving...' : 'Update Password'}
          </button>
        </form>
      </div>

      {/* Allow-list management */}
      <div className="bg-white rounded-lg shadow p-4">
        <h2 className="text-lg font-semibold mb-3">Allow-List Management</h2>
        <form onSubmit={handleAddEmail} className="flex flex-col gap-2 md:flex-row md:items-center mb-4">
          <input
            type="email"
            value={newEmail}
            onChange={(e) => setNewEmail(e.target.value)}
            placeholder="email@example.com"
            className="flex-1 rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
          />
          <button
            type="submit"
            disabled={savingEmail}
            className="px-4 py-2 bg-green-600 text-white rounded-md text-sm font-medium hover:bg-green-700 disabled:opacity-50"
          >
            {savingEmail ? 'Adding...' : 'Add to Allow-List'}
          </button>
        </form>
        {allowList.length === 0 ? (
          <p className="text-sm text-gray-500">No emails in allow-list yet.</p>
        ) : (
          <div className="space-y-2">
            {allowList.map((entry) => (
              <div
                key={entry.id}
                className="flex items-center justify-between rounded border border-gray-200 px-3 py-2 text-sm"
              >
                <div>
                  <div className="font-mono">{entry.email}</div>
                  <div className="text-xs text-gray-500">
                    Added {entry.created_at}
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => handleRemoveEmail(entry.id)}
                  className="px-2 py-1 text-xs bg-red-50 text-red-700 rounded hover:bg-red-100"
                >
                  Remove
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Audit logs */}
      <div className="bg-white rounded-lg shadow p-4">
        <h2 className="text-lg font-semibold mb-3">Recent Audit Logs</h2>
        {logs.length === 0 ? (
          <p className="text-sm text-gray-500">No audit logs recorded yet.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full text-xs">
              <thead>
                <tr className="bg-gray-50 text-gray-700">
                  <th className="px-2 py-1 text-left">Time</th>
                  <th className="px-2 py-1 text-left">Email</th>
                  <th className="px-2 py-1 text-left">Role</th>
                  <th className="px-2 py-1 text-left">Action</th>
                  <th className="px-2 py-1 text-left">Route</th>
                  <th className="px-2 py-1 text-left">IP</th>
                  <th className="px-2 py-1 text-left">Success</th>
                  <th className="px-2 py-1 text-left">Detail</th>
                </tr>
              </thead>
              <tbody>
                {logs.map((log) => (
                  <tr key={log.id} className="border-t border-gray-100">
                    <td className="px-2 py-1">{log.timestamp}</td>
                    <td className="px-2 py-1">{log.user_email || '—'}</td>
                    <td className="px-2 py-1">{log.role || '—'}</td>
                    <td className="px-2 py-1">{log.action || '—'}</td>
                    <td className="px-2 py-1">{log.route}</td>
                    <td className="px-2 py-1">{log.ip_address}</td>
                    <td className="px-2 py-1">
                      {log.success ? (
                        <span className="text-green-700">✔</span>
                      ) : (
                        <span className="text-red-700">✖</span>
                      )}
                    </td>
                    <td className="px-2 py-1 max-w-xs truncate" title={log.detail || ''}>
                      {log.detail || '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}










