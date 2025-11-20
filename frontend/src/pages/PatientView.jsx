import { useState, useEffect } from 'react'
import { useParams, Link } from 'react-router-dom'
import { Edit, ArrowLeft, BarChart3 } from 'lucide-react'
import { getPatient, getLabTimeline, generateSpecialistSummary } from '../utils/api'
import LabChart from '../components/LabChart'

export default function PatientView() {
  const { caseId } = useParams()
  const [patient, setPatient] = useState(null)
  const [loading, setLoading] = useState(true)
  const [timeline, setTimeline] = useState(null)
  const [error, setError] = useState(null)
  const [activeSpecialist, setActiveSpecialist] = useState(null)
  const [specialistSummaries, setSpecialistSummaries] = useState({})
  const [specialistStatus, setSpecialistStatus] = useState({})

  const specialistOptions = [
    { id: 'oncologist', label: 'Oncologist' },
    { id: 'hepatologist', label: 'Hepatologist' },
  ]

  useEffect(() => {
    if (caseId) {
      loadPatient()
      loadTimeline()
    }
  }, [caseId])

  const loadPatient = async () => {
    try {
      setError(null)
      const data = await getPatient(caseId)
      console.log('Patient data loaded:', data)
      setPatient(data)
    } catch (error) {
      console.error('Error loading patient:', error)
      setError(error.response?.data?.detail || error.message || 'Failed to load patient')
      setPatient(null)
    } finally {
      setLoading(false)
    }
  }
  const loadTimeline = async () => {
    try {
      const data = await getLabTimeline(caseId)
      console.log('Timeline data loaded:', data)
      setTimeline(data)
    } catch (error) {
      console.error('Error loading timeline:', error)
      // Don't fail the whole page if timeline fails
    }
  }

  const handleSpecialistSelect = async (specialistId) => {
    setActiveSpecialist(specialistId)

    // Avoid duplicate calls if we already have the summary
    if (specialistSummaries[specialistId] || specialistStatus[specialistId]?.loading) {
      return
    }

    setSpecialistStatus((prev) => ({
      ...prev,
      [specialistId]: { loading: true, error: null },
    }))

    try {
      const data = await generateSpecialistSummary(caseId, specialistId)
      setSpecialistSummaries((prev) => ({
        ...prev,
        [specialistId]: data,
      }))
      setSpecialistStatus((prev) => ({
        ...prev,
        [specialistId]: { loading: false, error: null },
      }))
    } catch (err) {
      console.error('Error generating specialist summary:', err)
      setSpecialistStatus((prev) => ({
        ...prev,
        [specialistId]: {
          loading: false,
          error: err.response?.data?.detail || err.message || 'Failed to generate summary',
        },
      }))
    }
  }

  const renderSummaryCard = (summary) => {
    if (!summary) return null

    const formattedDate = summary.generated_at
      ? new Date(summary.generated_at).toLocaleString()
      : '—'

    return (
      <div className="rounded-xl border border-gray-200 bg-gray-50 p-6">
        <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
          <div className="space-y-1">
            <p className="text-xs font-semibold uppercase tracking-wide text-blue-600">
              On-demand AI opinion
            </p>
            <h3 className="text-2xl font-bold text-gray-900">Diagnosis</h3>
          </div>
          <div className="flex flex-wrap gap-2 text-xs text-gray-600">
            {summary.confidence && (
              <span className="rounded-full bg-white px-3 py-1 font-medium shadow-sm">
                Confidence: {summary.confidence}
              </span>
            )}
            <span className="rounded-full bg-white px-3 py-1 font-medium shadow-sm">
              Model: {summary.source_model}
            </span>
            <span className="rounded-full bg-white px-3 py-1 font-medium shadow-sm">
              {formattedDate}
            </span>
          </div>
        </div>

        <div className="mt-4 rounded-lg bg-white p-4 shadow-sm">
          <p className="text-gray-900 whitespace-pre-wrap leading-relaxed">{summary.diagnosis}</p>
        </div>

        <div className="mt-6">
          <h4 className="text-lg font-semibold text-gray-900">Plan of Action</h4>
          <ol className="mt-3 space-y-3">
            {summary.suggestive_plan.map((item, idx) => (
              <li
                key={idx}
                className="flex gap-3 rounded-lg bg-white p-3 shadow-sm"
              >
                <span className="flex h-6 w-6 items-center justify-center rounded-full bg-blue-600 text-sm font-semibold text-white">
                  {idx + 1}
                </span>
                <p className="text-gray-800">{item}</p>
              </li>
            ))}
          </ol>
        </div>

        {summary.caveats && (
          <div className="mt-6 rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
            <p className="font-semibold uppercase tracking-wide">Caveats</p>
            <p className="mt-1 text-amber-900">{summary.caveats}</p>
          </div>
        )}
      </div>
    )
  }

  if (loading) {
    return <div className="flex justify-center py-12">Loading...</div>
  }

  if (error) {
    return (
      <div className="text-center py-12">
        <h1 className="text-2xl font-bold text-red-600 mb-4">Error Loading Patient</h1>
        <p className="text-gray-600 mb-4">{error}</p>
        <Link
          to="/"
          className="inline-flex items-center text-blue-600 hover:text-blue-700"
        >
          <ArrowLeft className="h-5 w-5 mr-2" />
          Back to List
        </Link>
      </div>
    )
  }

  if (!patient) {
    return (
      <div className="text-center py-12">
        <h1 className="text-2xl font-bold text-gray-900 mb-4">Patient Not Found</h1>
        <p className="text-gray-600 mb-4">The patient with case ID "{caseId}" could not be found.</p>
        <Link
          to="/"
          className="inline-flex items-center text-blue-600 hover:text-blue-700"
        >
          <ArrowLeft className="h-5 w-5 mr-2" />
          Back to List
        </Link>
      </div>
    )
  }

  // Debug: Log patient data
  console.log('Rendering PatientView with patient:', patient)
  console.log('CaseId:', caseId)
  console.log('Timeline:', timeline)

  return (
    <div>
      <div className="flex justify-between items-center mb-6">
        <Link
          to="/"
          className="flex items-center text-blue-600 hover:text-blue-700"
        >
          <ArrowLeft className="h-5 w-5 mr-2" />
          Back to List
        </Link>
        <Link
          to={`/patient/${caseId}/edit`}
          className="flex items-center px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
        >
          <Edit className="h-5 w-5 mr-2" />
          Edit
        </Link>
      </div>

      <h1 className="text-3xl font-bold text-gray-900 mb-6">
        Patient Entity: {patient?.case_id || caseId}
      </h1>

      <div className="grid gap-6">
        {patient.demographics && (
          <div className="bg-white rounded-lg shadow p-6">
            <h2 className="text-xl font-semibold mb-4">Demographics</h2>
            <div className="grid grid-cols-3 gap-4">
              <div>
                <span className="text-gray-600">Age:</span>{' '}
                <span className="font-medium">{patient.demographics.age || 'N/A'}</span>
              </div>
              <div>
                <span className="text-gray-600">Sex:</span>{' '}
                <span className="font-medium">{patient.demographics.sex || 'N/A'}</span>
              </div>
            </div>
          </div>
        )}

        {patient.clinical_summary && (
          <div className="bg-white rounded-lg shadow p-6">
            <h2 className="text-xl font-semibold mb-4">Clinical Summary</h2>
            <div className="space-y-2">
              <div>
                <span className="text-gray-600">Etiology:</span>{' '}
                <span className="font-medium">
                  {patient.clinical_summary.etiology || 'N/A'}
                </span>
              </div>
              {patient.clinical_summary.symptoms && patient.clinical_summary.symptoms.length > 0 && (
                <div>
                  <span className="text-gray-600">Symptoms:</span>{' '}
                  <span className="font-medium">
                    {patient.clinical_summary.symptoms.join(', ')}
                  </span>
                </div>
              )}
              {patient.clinical_summary.comorbidities && patient.clinical_summary.comorbidities.length > 0 && (
                <div>
                  <span className="text-gray-600">Comorbidities:</span>{' '}
                  <span className="font-medium">
                    {patient.clinical_summary.comorbidities.join(', ')}
                  </span>
                </div>
              )}
            </div>
          </div>
        )}

        {patient.lab_data && (
          <div className="bg-white rounded-lg shadow p-6">
            <div className="flex items-center mb-4">
              <BarChart3 className="h-6 w-6 mr-2 text-blue-600" />
              <h2 className="text-xl font-semibold">Lab Data</h2>
            </div>
            {timeline && timeline.timeline && Array.isArray(timeline.timeline) && timeline.timeline.length > 0 && (
              <LabChart timeline={timeline.timeline} />
            )}
            {patient.lab_data.baseline && (
              <div className="mt-4">
                <h3 className="font-semibold mb-2">Baseline Values</h3>
                <div className="grid grid-cols-3 gap-4 text-sm">
                  <div>ALT: {patient.lab_data.baseline.ALT || 'N/A'}</div>
                  <div>AST: {patient.lab_data.baseline.AST || 'N/A'}</div>
                  <div>Tbil: {patient.lab_data.baseline.Tbil || 'N/A'}</div>
                  <div>Alb: {patient.lab_data.baseline.Alb || 'N/A'}</div>
                  <div>PT: {patient.lab_data.baseline.PT || 'N/A'}</div>
                  <div>INR: {patient.lab_data.baseline.INR || 'N/A'}</div>
                </div>
              </div>
            )}
            {patient.lab_data.derived_scores && (
              <div className="mt-4">
                <h3 className="font-semibold mb-2">Derived Scores</h3>
                <div className="grid grid-cols-3 gap-4 text-sm">
                  <div>CTP: {patient.lab_data.derived_scores.CTP || 'N/A'}</div>
                  <div>MELD_Na: {patient.lab_data.derived_scores.MELD_Na || 'N/A'}</div>
                  <div>AFP: {patient.lab_data.derived_scores.AFP || 'N/A'}</div>
                </div>
              </div>
            )}
          </div>
        )}

        <div className="bg-white rounded-lg shadow p-6">
          <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between mb-4">
            <div>
              <h2 className="text-xl font-semibold">Specialist AI Summaries</h2>
              <p className="text-sm text-gray-500">
                Select a specialist to generate a concise diagnosis and plan tailored to this patient.
              </p>
            </div>
            <p className="text-xs text-gray-400">Powered by your OpenAI GPT-4 key</p>
          </div>
          <div className="flex flex-wrap gap-3">
            {specialistOptions.map((option) => {
              const status = specialistStatus[option.id]
              const isActive = activeSpecialist === option.id
              return (
                <button
                  key={option.id}
                  type="button"
                  onClick={() => handleSpecialistSelect(option.id)}
                  className={`px-4 py-2 rounded-lg border text-sm font-medium transition-all ${
                    isActive
                      ? 'bg-blue-600 text-white border-blue-600 shadow-lg shadow-blue-100'
                      : 'bg-white text-gray-700 border-gray-200 hover:border-blue-400 hover:shadow'
                  }`}
                >
                  {status?.loading ? `Generating ${option.label}...` : option.label}
                </button>
              )
            })}
          </div>
          <div className="mt-6 border-t pt-4">
            {activeSpecialist ? (
              (() => {
                const activeStatus = specialistStatus[activeSpecialist]
                const summary = specialistSummaries[activeSpecialist]
                const activeLabel =
                  specialistOptions.find((opt) => opt.id === activeSpecialist)?.label ||
                  activeSpecialist

                if (activeStatus?.error) {
                  return (
                    <div className="text-red-600 text-sm">
                      {activeStatus.error}. Please try again or check the server logs.
                    </div>
                  )
                }

                if (activeStatus?.loading) {
                  return <div className="text-gray-600 text-sm">Generating summary...</div>
                }

                if (!summary) {
                  return (
                    <div className="rounded-lg border border-dashed border-gray-300 bg-gray-50 p-6 text-gray-600 text-sm">
                      Click "{activeLabel}" to generate their recommendations.
                    </div>
                  )
                }

                return renderSummaryCard(summary)
              })()
            ) : (
              <div className="rounded-lg border border-dashed border-gray-300 bg-gray-50 p-6 text-gray-600 text-sm">
                Choose a specialist above to generate a tailored AI summary.
              </div>
            )}
          </div>
        </div>

        {patient.imaging && (
          <div className="bg-white rounded-lg shadow p-6">
            <h2 className="text-xl font-semibold mb-4">Imaging</h2>
            <div className="space-y-2">
              <div>
                <span className="text-gray-600">Modality:</span>{' '}
                <span className="font-medium">{patient.imaging.modality || 'N/A'}</span>
              </div>
              {patient.imaging.findings && patient.imaging.findings.length > 0 && (
                <div>
                  <h3 className="font-semibold mt-4 mb-2">Findings</h3>
                  {patient.imaging.findings.map((finding, idx) => (
                    <div key={idx} className="bg-gray-50 p-4 rounded mb-2">
                      <div className="grid grid-cols-2 gap-2 text-sm">
                        <div>Date: {finding.date || 'N/A'}</div>
                        <div>Lesions: {finding.lesion_count || 'N/A'}</div>
                        <div>Size: {finding.largest_size_cm || 'N/A'} cm</div>
                        <div>Segment: {finding.segment || 'N/A'}</div>
                        <div>LI-RADS: {finding.LIRADS || 'N/A'}</div>
                        <div>PVTT: {finding.PVTT ? 'Yes' : 'No'}</div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}

        {patient.treatment_history && (
          <div className="bg-white rounded-lg shadow p-6">
            <h2 className="text-xl font-semibold mb-4">Treatment History</h2>
            <div className="space-y-2">
              {patient.treatment_history.previous && patient.treatment_history.previous.length > 0 && (
                <div>
                  <span className="text-gray-600">Previous:</span>{' '}
                  <span className="font-medium">
                    {patient.treatment_history.previous.join(', ')}
                  </span>
                </div>
              )}
              <div>
                <span className="text-gray-600">Current:</span>{' '}
                <span className="font-medium">
                  {patient.treatment_history.current || 'N/A'}
                </span>
              </div>
              <div>
                <span className="text-gray-600">Response Summary:</span>{' '}
                <span className="font-medium">
                  {patient.treatment_history.response_summary || 'N/A'}
                </span>
              </div>
            </div>
          </div>
        )}

        {patient.tumor_board_notes && (
          <div className="bg-white rounded-lg shadow p-6">
            <h2 className="text-xl font-semibold mb-4">Tumor Board Notes</h2>
            <div className="space-y-4">
              {patient.tumor_board_notes.discussion && (
                <div>
                  <h3 className="font-semibold mb-2">Discussion</h3>
                  <p className="text-gray-700 whitespace-pre-wrap">
                    {patient.tumor_board_notes.discussion}
                  </p>
                </div>
              )}
              {patient.tumor_board_notes.recommendation && (
                <div>
                  <h3 className="font-semibold mb-2">Recommendation</h3>
                  <p className="text-gray-700 whitespace-pre-wrap">
                    {patient.tumor_board_notes.recommendation}
                  </p>
                </div>
              )}
              {patient.tumor_board_notes.board_members && patient.tumor_board_notes.board_members.length > 0 && (
                <div>
                  <h3 className="font-semibold mb-2">Board Members</h3>
                  <p className="text-gray-700">
                    {patient.tumor_board_notes.board_members.join(', ')}
                  </p>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}