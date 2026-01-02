import { useEffect, useState } from 'react'
import axios from 'axios'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../contexts/AuthContext'

const API_BASE_URL = 'http://localhost:8000'
const GOOGLE_CLIENT_ID = import.meta.env.VITE_GOOGLE_CLIENT_ID

export default function UserLogin() {
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(false)
  const navigate = useNavigate()
  const { login, isAuthenticated } = useAuth()

  // Redirect if already authenticated
  useEffect(() => {
    if (isAuthenticated) {
      navigate('/patients', { replace: true })
    }
  }, [isAuthenticated, navigate])

  useEffect(() => {
    if (!GOOGLE_CLIENT_ID) {
      setError('VITE_GOOGLE_CLIENT_ID is not configured in the frontend environment.')
      return
    }

    // Dynamically load Google Identity Services script
    const existing = document.querySelector('script[data-google-identity]')
    if (existing) return

    const script = document.createElement('script')
    script.src = 'https://accounts.google.com/gsi/client'
    script.async = true
    script.defer = true
    script.dataset.googleIdentity = 'true'
    script.onload = () => {
      /* global google */
      if (window.google && window.google.accounts && window.google.accounts.id) {
        window.google.accounts.id.initialize({
          client_id: GOOGLE_CLIENT_ID,
          callback: handleGoogleCredentialResponse,
        })
        window.google.accounts.id.renderButton(
          document.getElementById('google-signin-button'),
          {
            type: 'standard',
            theme: 'outline',
            size: 'large',
            width: '250',
          }
        )
        window.google.accounts.id.prompt()
      } else {
        setError('Failed to initialize Google Identity Services.')
      }
    }
    script.onerror = () => setError('Failed to load Google Identity script.')

    document.body.appendChild(script)

    return () => {
      // No official teardown required; button will be removed with component
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const handleGoogleCredentialResponse = async (response) => {
    const idToken = response.credential
    if (!idToken) {
      setError('No credential returned from Google.')
      return
    }

    setLoading(true)
    setError(null)
    try {
      // Step 1: Authenticate with Google token
      const loginResponse = await axios.post(
        `${API_BASE_URL}/auth/login/google`,
        { id_token: idToken },
        { withCredentials: true }
      )

      // Step 2: Verify session was established
      const sessionResponse = await axios.get(
        `${API_BASE_URL}/auth/me`,
        { withCredentials: true }
      )

      // Step 3: Update auth context
      await login(sessionResponse.data)

      // Step 4: Redirect to dashboard only after session is verified
      navigate('/patients', { replace: true })
    } catch (err) {
      console.error('Google login failed', err)
      setError(
        err.response?.data?.detail || err.message || 'Login failed. Please try again.'
      )
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="max-w-md mx-auto mt-12 bg-white rounded-lg shadow p-6">
      <h1 className="text-2xl font-bold mb-4 text-gray-900">User Login</h1>
      <p className="text-sm text-gray-600 mb-4">
        Sign in with your Google account. Access is granted only if your email is in the
        server-side allow-list.
      </p>

      {error && (
        <div className="text-sm text-red-600 bg-red-50 border border-red-200 rounded px-3 py-2 mb-3">
          {error}
        </div>
      )}

      <div className="flex flex-col items-center gap-3">
        <div id="google-signin-button" />
        {loading && (
          <div className="text-sm text-gray-600">Completing sign-in...</div>
        )}
      </div>

      {!GOOGLE_CLIENT_ID && (
        <p className="mt-4 text-xs text-red-700 bg-red-50 border border-red-200 rounded px-3 py-2">
          Frontend Google OAuth is not fully configured. Set{' '}
          <code className="font-mono">VITE_GOOGLE_CLIENT_ID</code> in your frontend
          environment to match the `GOOGLE_CLIENT_ID` used on the backend.
        </p>
      )}
    </div>
  )
}


