import axios from 'axios'

const API_BASE_URL = 'http://localhost:8000'

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
})

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