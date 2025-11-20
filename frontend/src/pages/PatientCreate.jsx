import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { createPatient } from '../utils/api'
import PatientForm from '../components/PatientForm'

export default function PatientCreate() {
  const navigate = useNavigate()
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (data) => {
    setLoading(true)
    try {
      console.log('Submitting patient data:', JSON.stringify(data, null, 2))
      await createPatient(data)
      navigate('/')
    } catch (error) {
      console.error('Error creating patient:', error)
      let errorMessage = 'Failed to create patient. Please try again.'
      
      if (error.response?.data) {
        const errorData = error.response.data
        if (errorData.detail) {
          if (Array.isArray(errorData.detail)) {
            // Validation errors from Pydantic
            const validationErrors = errorData.detail.map(err => 
              `${err.loc?.join('.')}: ${err.msg}`
            ).join('\n')
            errorMessage = `Validation errors:\n${validationErrors}`
          } else {
            errorMessage = errorData.detail
          }
        }
      }
      
      alert(errorMessage)
      setLoading(false)
    }
  }

  return (
    <div>
      <h1 className="text-3xl font-bold text-gray-900 mb-6">Create New Patient Entity</h1>
      <PatientForm onSubmit={handleSubmit} loading={loading} />
    </div>
  )
}
