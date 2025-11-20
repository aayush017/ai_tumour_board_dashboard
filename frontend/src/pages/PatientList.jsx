import { useState, useEffect } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Trash2, Edit, Eye, Plus } from 'lucide-react'
import { getPatients, deletePatient } from '../utils/api'

export default function PatientList() {
  const [patients, setPatients] = useState([])
  const [loading, setLoading] = useState(true)
  const navigate = useNavigate()

  useEffect(() => {
    loadPatients()
  }, [])

  const loadPatients = async () => {
    try {
      const data = await getPatients()
      setPatients(data)
    } catch (error) {
      console.error('Error loading patients:', error)
    } finally {
      setLoading(false)
    }
  }

  const handleDelete = async (caseId) => {
    if (window.confirm('Are you sure you want to delete this patient?')) {
      try {
        await deletePatient(caseId)
        setPatients(patients.filter(p => p.case_id !== caseId))
      } catch (error) {
        console.error('Error deleting patient:', error)
        alert('Failed to delete patient')
      }
    }
  }

  if (loading) {
    return <div className="flex justify-center py-12">Loading...</div>
  }

  return (
    <div>
      <div className="flex justify-between items-center mb-6">
        <h1 className literal="text-3xl font-bold text-gray-900">Patient Entities</h1>
        <Link
          to="/create"
          className="flex items-center px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
        >
          <Plus className="h-5 w-5 mr-2" />
          Add New Patient
        </Link>
      </div>

      {patients.length === 0 ? (
        <div className="text-center py-12 bg-white rounded-lg shadow">
          <p className="text-gray-500 mb-4">No patients found</p>
          <Link
            to="/create"
            className="text-blue-600 hover:text-blue-700 font-medium"
          >
            Create your first patient entity
          </Link>
        </div>
      ) : (
        <div className="grid gap-4">
          {patients.map((patient) => (
            <div
              key={patient.id}
              className="bg-white rounded-lg shadow p-6 hover:shadow-md transition-shadow"
            >
              <div className="flex justify-between items-start">
                <div className="flex-1">
                  <h2 className="text-xl font-semibold text-gray-900">
                    {patient.case_id}
                  </h2>
                  {patient.demographics && (
                    <div className="mt-2 text-sm text-gray-600">
                      <span>
                        Age: {patient.demographics.age || 'N/A'}, Sex:{' '}
                        {patient.demographics.sex || 'N/A'}
                      </span>
                    </div>
                  )}
                  {patient.clinical_summary && (
                    <div className="mt-2 text-sm text-gray-600">
                      <span>Etiology: {patient.clinical_summary.etiology || 'N/A'}</span>
                    </div>
                  )}
                </div>
                <div className="flex space-x-2">
                  <Link
                    to={`/patient/${patient.case_id}`}
                    className="p-2 text-blue-600 hover:bg-blue-50 rounded"
                    title="View"
                  >
                    <Eye className="h-5 w-5" />
                  </Link>
                  <Link
                    to={`/patient/${patient.case_id}/edit`}
                    className="p-2 text-green-600 hover:bg-green-50 rounded"
                    title="Edit"
                  >
                    <Edit className="h-5 w-5" />
                  </Link>
                  <button
                    onClick={() => handleDelete(patient.case_id)}
                    className="p-2 text-red-600 hover:bg-red-50 rounded"
                    title="Delete"
                  >
                    <Trash2 className="h-5 w-5" />
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
