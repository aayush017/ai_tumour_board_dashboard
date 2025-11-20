import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { getPatient, updatePatient } from '../utils/api'
import PatientForm from '../components/PatientForm'

export default function PatientEdit() {
  const { caseId } = useParams()
  const navigate = useNavigate()
  const [patient, setPatient] = useState(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    loadPatient()
  }, [caseId])

  const loadPatient = async () => {
    try {
      const data = await getPatient(caseId)
      setPatient(data)
    } catch (error) {
      console.error('Error loading patient:', error)
    } finally {
      setLoading(false)
    }
  }

  const handleSubmit = async (data) => {
    setSaving(true)
    try {
      await updatePatient(caseId, data)
      navigate(`/patient/${caseId}`)
    } catch (error) {
      console.error('Error updating patient:', error)
      alert('Failed to update patient. Please try again.')
      setSaving(false)
    }
  }

  if (loading) {
    return <div className="flex justify-center py-12">Loading...</div>
  }

  return (
    <div>
      <h1 className="text-3xl font-bold text-gray-900 mb-6">
        Edit Patient Entity: {patient.case_id}
      </h1>
      <PatientForm patient={patient} onSubmit={handleSubmit} loading={saving} />
    </div>
  )
}
