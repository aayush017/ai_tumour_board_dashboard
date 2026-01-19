import axios from 'axios'

const API_BASE_URL = 'http://localhost:8000'

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
  withCredentials: true, // Include cookies in all requests
})

// Add response interceptor to handle 401 errors
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    if (error.response?.status === 401) {
      // Clear any stale auth state
      if (window.location.pathname !== '/login' && window.location.pathname !== '/master/login') {
        // Only redirect if not already on a login page
        window.location.href = '/login'
      }
    }
    return Promise.reject(error)
  }
)

export const getPatients = async () => {
  const response = await api.get('/api/patients')
  return response.data
}

export const getPatient = async (caseId) => {
  const response = await api.get(`/api/patients/${caseId}`)
  return response.data
}

export const createPatient = async (patientData) => {
  const response = await api.post('/api/patients', patientData)
  return response.data
}

export const updatePatient = async (caseId, patientData) => {
  const response = await api.put(`/api/patients/${caseId}`, patientData)
  return response.data
}

export const deletePatient = async (caseId) => {
  const response = await api.delete(`/api/patients/${caseId}`)
  return response.data
}

export const getLabTimeline = async (caseId) => {
  const response = await api.get(`/api/patients/${caseId}/lab-timeline`)
  return response.data
}

export const generateSpecialistSummary = async (caseId, specialist) => {
  const response = await api.post(`/api/patients/${caseId}/specialists/${specialist}/summary`)
  return response.data
}

export const generateAgentSummary = async (caseId) => {
  const response = await api.post(`/api/patients/${caseId}/agent-summary`)
  return response.data
}

export const previewAgentSummary = async (caseId) => {
  const response = await api.post(`/api/patients/${caseId}/agent-summary/preview`)
  return response.data
}

export const approveAgentSummary = async (caseId, agentOutput) => {
  const response = await api.post(`/api/patients/${caseId}/agent-summary/approve`, agentOutput)
  return response.data
}