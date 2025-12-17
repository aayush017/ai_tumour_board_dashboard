import { useState, useEffect, useMemo } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Trash2, Edit, Eye, Plus } from 'lucide-react'
import { getPatients, deletePatient } from '../utils/api'

export default function PatientList() {
  const [patients, setPatients] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  // UI state for search / filter / sort / pagination
  const [searchTerm, setSearchTerm] = useState('')
  const [sexFilter, setSexFilter] = useState('all')
  const [sortKey, setSortKey] = useState('created_desc') // created_desc | case_asc | age_desc | age_asc
  const [currentPage, setCurrentPage] = useState(1)
  const pageSize = 10

  const navigate = useNavigate()

  useEffect(() => {
    loadPatients()
  }, [])

  const loadPatients = async () => {
    try {
      setError(null)
      const data = await getPatients()
      setPatients(Array.isArray(data) ? data : [])
    } catch (err) {
      console.error('Error loading patients:', err)
      setError(err.response?.data?.detail || err.message || 'Failed to load patients')
    } finally {
      setLoading(false)
    }
  }

  const handleDelete = async (caseId) => {
    if (window.confirm('Are you sure you want to delete this patient?')) {
      try {
        await deletePatient(caseId)
        setPatients((prev) => prev.filter((p) => p.case_id !== caseId))
      } catch (err) {
        console.error('Error deleting patient:', err)
        alert('Failed to delete patient')
      }
    }
  }

  // Derived list with search + filter + sort
  const processedPatients = useMemo(() => {
    let list = [...patients]

    // Search by case_id, name, etiology
    if (searchTerm.trim()) {
      const term = searchTerm.trim().toLowerCase()
      list = list.filter((p) => {
        const caseId = p.case_id?.toLowerCase() || ''
        const name = p.demographics?.name?.toLowerCase() || ''
        const etiology = p.clinical?.etiology?.toLowerCase() || ''
        return (
          caseId.includes(term) ||
          name.includes(term) ||
          etiology.includes(term)
        )
      })
    }

    // Filter by sex
    if (sexFilter !== 'all') {
      list = list.filter((p) => {
        const sex = (p.demographics?.sex || '').toString().toLowerCase()
        if (!sex) return false
        if (sexFilter === 'male') return sex === 'm' || sex === 'male'
        if (sexFilter === 'female') return sex === 'f' || sex === 'female'
        if (sexFilter === 'other') return sex === 'other'
        return true
      })
    }

    // Sort
    list.sort((a, b) => {
      const createdA = a.created_at ? new Date(a.created_at).getTime() : 0
      const createdB = b.created_at ? new Date(b.created_at).getTime() : 0
      const ageA = Number(a.demographics?.age ?? NaN)
      const ageB = Number(b.demographics?.age ?? NaN)

      switch (sortKey) {
        case 'case_asc':
          return (a.case_id || '').localeCompare(b.case_id || '')
        case 'age_desc':
          if (isNaN(ageA) && isNaN(ageB)) return 0
          if (isNaN(ageA)) return 1
          if (isNaN(ageB)) return -1
          return ageB - ageA
        case 'age_asc':
          if (isNaN(ageA) && isNaN(ageB)) return 0
          if (isNaN(ageA)) return 1
          if (isNaN(ageB)) return -1
          return ageA - ageB
        case 'created_asc':
          return createdA - createdB
        case 'created_desc':
        default:
          return createdB - createdA
      }
    })

    return list
  }, [patients, searchTerm, sexFilter, sortKey])

  // Pagination
  const totalItems = processedPatients.length
  const totalPages = Math.max(1, Math.ceil(totalItems / pageSize))
  const currentSafePage = Math.min(currentPage, totalPages)
  const startIndex = (currentSafePage - 1) * pageSize
  const pageItems = processedPatients.slice(startIndex, startIndex + pageSize)

  const handlePageChange = (newPage) => {
    if (newPage < 1 || newPage > totalPages) return
    setCurrentPage(newPage)
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  if (loading) {
    return <div className="flex justify-center py-12">Loading...</div>
  }

  return (
    <div>
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-3xl font-bold text-gray-900">Patient Entities</h1>
        <Link
          to="/create"
          className="flex items-center px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
        >
          <Plus className="h-5 w-5 mr-2" />
          Add New Patient
        </Link>
      </div>

      {/* Search / Filter / Sort */}
      <div className="bg-white rounded-lg shadow p-4 mb-6 flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
        <div className="flex-1">
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Search
          </label>
          <input
            type="text"
            value={searchTerm}
            onChange={(e) => {
              setSearchTerm(e.target.value)
              setCurrentPage(1)
            }}
            placeholder="Search by Case ID, name, or etiology..."
            className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
          />
        </div>

        <div className="flex flex-col gap-3 md:flex-row md:items-end">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Filter by Sex
            </label>
            <select
              value={sexFilter}
              onChange={(e) => {
                setSexFilter(e.target.value)
                setCurrentPage(1)
              }}
              className="rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            >
              <option value="all">All</option>
              <option value="male">Male</option>
              <option value="female">Female</option>
              <option value="other">Other</option>
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Sort by
            </label>
            <select
              value={sortKey}
              onChange={(e) => {
                setSortKey(e.target.value)
                setCurrentPage(1)
              }}
              className="rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            >
              <option value="created_desc">Created (Newest)</option>
              <option value="created_asc">Created (Oldest)</option>
              <option value="case_asc">Case ID (A–Z)</option>
              <option value="age_desc">Age (High to Low)</option>
              <option value="age_asc">Age (Low to High)</option>
            </select>
          </div>
        </div>
      </div>

      {error && (
        <div className="mb-4 rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      )}

      {pageItems.length === 0 ? (
        <div className="text-center py-12 bg-white rounded-lg shadow">
          <p className="text-gray-500 mb-4">
            No patients found matching your criteria.
          </p>
          <button
            type="button"
            onClick={() => {
              setSearchTerm('')
              setSexFilter('all')
              setSortKey('created_desc')
              setCurrentPage(1)
            }}
            className="text-blue-600 hover:text-blue-700 font-medium"
          >
            Clear filters
          </button>
        </div>
      ) : (
        <>
          <div className="grid gap-4">
            {pageItems.map((patient) => (
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
                    {patient.clinical && (
                      <div className="mt-2 text-sm text-gray-600">
                        <span>Etiology: {patient.clinical.etiology || 'N/A'}</span>
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

          {/* Pagination controls */}
          <div className="mt-6 flex flex-col items-center gap-3 md:flex-row md:justify-between">
            <p className="text-sm text-gray-600">
              Showing{' '}
              <span className="font-medium">
                {startIndex + 1}-{Math.min(startIndex + pageSize, totalItems)}
              </span>{' '}
              of <span className="font-medium">{totalItems}</span> patients
            </p>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => handlePageChange(currentSafePage - 1)}
                disabled={currentSafePage === 1}
                className="px-3 py-1 rounded-md border text-sm disabled:opacity-50 disabled:cursor-not-allowed hover:bg-gray-50"
              >
                Previous
              </button>
              <span className="text-sm text-gray-700">
                Page <span className="font-semibold">{currentSafePage}</span> of{' '}
                <span className="font-semibold">{totalPages}</span>
              </span>
              <button
                type="button"
                onClick={() => handlePageChange(currentSafePage + 1)}
                disabled={currentSafePage === totalPages}
                className="px-3 py-1 rounded-md border text-sm disabled:opacity-50 disabled:cursor-not-allowed hover:bg-gray-50"
              >
                Next
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
