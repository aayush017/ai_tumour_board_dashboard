import { useState, useEffect } from 'react'
import { useParams, Link } from 'react-router-dom'
import { Edit, ArrowLeft, BarChart3 } from 'lucide-react'
import { getPatient, getLabTimeline, generateSpecialistSummary, generateAgentSummary } from '../utils/api'
import LabChart from '../components/LabChart'

const labBaselineFields = [
  { key: 'hemoglobin_g_dl', label: 'Hemoglobin (g/dL)' },
  { key: 'WBC_k', label: 'WBC (k)' },
  { key: 'platelets_k', label: 'Platelets (k)' },
  { key: 'total_bilirubin_mg_dl', label: 'Total Bilirubin (mg/dL)' },
  { key: 'direct_bilirubin_mg_dl', label: 'Direct Bilirubin (mg/dL)' },
  { key: 'AST_U_L', label: 'AST (U/L)' },
  { key: 'ALT_U_L', label: 'ALT (U/L)' },
  { key: 'ALP_U_L', label: 'ALP (U/L)' },
  { key: 'albumin_g_dl', label: 'Albumin (g/dL)' },
  { key: 'INR', label: 'INR' },
  { key: 'PT_sec', label: 'PT (sec)' },
  { key: 'Na_mmol_L', label: 'Sodium (mmol/L)' },
  { key: 'creatinine_mg_dl', label: 'Creatinine (mg/dL)' },
  { key: 'AFP_ng_ml', label: 'AFP (ng/mL)' },
  { key: 'CRP_mg_L', label: 'CRP (mg/L)' },
]

export default function PatientView() {
  const { caseId } = useParams()
  const [patient, setPatient] = useState(null)
  const [loading, setLoading] = useState(true)
  const [timeline, setTimeline] = useState(null)
  const [error, setError] = useState(null)
  const [activeSpecialist, setActiveSpecialist] = useState(null)
  const [specialistSummaries, setSpecialistSummaries] = useState({})
  const [specialistStatus, setSpecialistStatus] = useState({})
  const [agentSummary, setAgentSummary] = useState(null)
  const [agentSummaryLoading, setAgentSummaryLoading] = useState(false)
  const [agentSummaryError, setAgentSummaryError] = useState(null)

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

  const handleLoadAgentSummary = async () => {
    if (agentSummaryLoading || agentSummary) return

    setAgentSummaryLoading(true)
    setAgentSummaryError(null)

    try {
      const data = await generateAgentSummary(caseId)
      setAgentSummary(data)
    } catch (err) {
      console.error('Error generating agent summary:', err)
      setAgentSummaryError(err.response?.data?.detail || err.message || 'Failed to generate agent summary')
    } finally {
      setAgentSummaryLoading(false)
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
            <div className="grid grid-cols-2 gap-4">
              <div>
                <span className="text-gray-600">Name:</span>{' '}
                <span className="font-medium">{patient.demographics.name || 'N/A'}</span>
              </div>
              <div>
                <span className="text-gray-600">Age:</span>{' '}
                <span className="font-medium">{patient.demographics.age || 'N/A'}</span>
              </div>
              <div>
                <span className="text-gray-600">Sex:</span>{' '}
                <span className="font-medium">{patient.demographics.sex || 'N/A'}</span>
              </div>
              <div>
                <span className="text-gray-600">BMI:</span>{' '}
                <span className="font-medium">{patient.demographics.BMI ?? 'N/A'}</span>
              </div>
            </div>
          </div>
        )}

        {patient.clinical && (
          <div className="bg-white rounded-lg shadow p-6">
            <h2 className="text-xl font-semibold mb-4">Clinical</h2>
            <div className="space-y-2">
              <div>
                <span className="text-gray-600">Etiology:</span>{' '}
                <span className="font-medium">
                  {patient.clinical.etiology || 'N/A'}
                </span>
              </div>
              {patient.clinical.symptoms && patient.clinical.symptoms.length > 0 && (
                <div>
                  <span className="text-gray-600">Symptoms:</span>{' '}
                  <span className="font-medium">
                    {patient.clinical.symptoms.join(', ')}
                  </span>
                </div>
              )}
              {patient.clinical.comorbidities && patient.clinical.comorbidities.length > 0 && (
                <div>
                  <span className="text-gray-600">Comorbidities:</span>{' '}
                  <span className="font-medium">
                    {patient.clinical.comorbidities.join(', ')}
                  </span>
                </div>
              )}
              <div className="grid grid-cols-3 gap-4 text-sm pt-2">
                <div>Ascites: {patient.clinical.ascites || 'N/A'}</div>
                <div>Encephalopathy: {patient.clinical.encephalopathy || 'N/A'}</div>
                <div>ECOG: {patient.clinical.ECOG ?? 'N/A'}</div>
              </div>
              {patient.clinical.clinical_notes_text && (
                <div className="pt-2">
                  <span className="text-gray-600 block mb-1">Clinical Notes:</span>
                  <p className="text-gray-800 whitespace-pre-wrap">
                    {patient.clinical.clinical_notes_text}
                  </p>
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
                  {labBaselineFields.map(({ key, label }) => (
                    <div key={key}>
                      {label}: {patient.lab_data.baseline[key] ?? 'N/A'}
                    </div>
                  ))}
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

        {/* Comprehensive Agent Summary Section */}
        <div className="bg-white rounded-lg shadow p-6">
          <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between mb-4">
            <div>
              <h2 className="text-xl font-semibold">Comprehensive Agent Analysis</h2>
              <p className="text-sm text-gray-500">
                Generate a comprehensive analysis using all four agents: Radiology, Clinical, Pathology, and Tumor Board.
              </p>
            </div>
          </div>
          
          {!agentSummary && !agentSummaryLoading && (
            <button
              type="button"
              onClick={handleLoadAgentSummary}
              className="px-6 py-3 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700 transition-colors shadow-sm"
            >
              Generate Comprehensive Analysis
            </button>
          )}

          {agentSummaryLoading && (
            <div className="text-gray-600 text-sm py-4">Generating comprehensive analysis... This may take a moment.</div>
          )}

          {agentSummaryError && (
            <div className="text-red-600 text-sm py-4 bg-red-50 rounded-lg p-4">
              Error: {agentSummaryError}
            </div>
          )}

          {agentSummary && (
            <div className="mt-6 space-y-6">
              {/* Culminated Plan of Action */}
              {agentSummary.culminated_plan_of_action && (
                <div className="border-t pt-6">
                  <h3 className="text-lg font-semibold mb-3 text-blue-600">Culminated Plan of Action</h3>
                  <div className="bg-blue-50 rounded-lg p-4 mb-4">
                    <p className="text-gray-900 whitespace-pre-wrap leading-relaxed">
                      {agentSummary.culminated_plan_of_action.summary}
                    </p>
                  </div>
                  
                  {agentSummary.culminated_plan_of_action.recommendations && 
                   agentSummary.culminated_plan_of_action.recommendations.length > 0 && (
                    <div className="mt-4">
                      <h4 className="font-semibold mb-2">Recommendations:</h4>
                      <ul className="list-disc list-inside space-y-1 text-gray-700">
                        {agentSummary.culminated_plan_of_action.recommendations.map((rec, idx) => (
                          <li key={idx}>{rec}</li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {agentSummary.culminated_plan_of_action.key_findings && 
                   agentSummary.culminated_plan_of_action.key_findings.length > 0 && (
                    <div className="mt-4">
                      <h4 className="font-semibold mb-2">Key Findings:</h4>
                      <ul className="list-disc list-inside space-y-1 text-gray-700">
                        {agentSummary.culminated_plan_of_action.key_findings.map((finding, idx) => (
                          <li key={idx}>{finding}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              )}

              {/* Individual Agent Responses */}
              <div className="border-t pt-6">
                <h3 className="text-lg font-semibold mb-4">Individual Agent Responses</h3>
                
                <div className="space-y-6">
                  {/* Radiology */}
                  {agentSummary.agent_responses?.radiology && (
                    <div className="border rounded-lg p-4">
                      <h4 className="font-semibold text-blue-600 mb-2">Radiology Agent</h4>
                      {agentSummary.agent_responses.radiology.radiology_summary?.radiology_interpretation && (
                        <p className="text-gray-700 text-sm">
                          {agentSummary.agent_responses.radiology.radiology_summary.radiology_interpretation}
                        </p>
                      )}
                      {agentSummary.agent_metadata?.radiology_confidence !== null && (
                        <p className="text-xs text-gray-500 mt-2">
                          Confidence: {agentSummary.agent_metadata.radiology_confidence}
                        </p>
                      )}
                    </div>
                  )}

                  {/* Clinical */}
                  {agentSummary.agent_responses?.clinical && (
                    <div className="border rounded-lg p-4">
                      <h4 className="font-semibold text-green-600 mb-2">Clinical Agent</h4>
                      {agentSummary.agent_responses.clinical.clinical_summary?.clinical_interpretation && (
                        <p className="text-gray-700 text-sm">
                          {agentSummary.agent_responses.clinical.clinical_summary.clinical_interpretation}
                        </p>
                      )}
                      {agentSummary.agent_metadata?.clinical_confidence !== null && (
                        <p className="text-xs text-gray-500 mt-2">
                          Confidence: {agentSummary.agent_metadata.clinical_confidence}
                        </p>
                      )}
                    </div>
                  )}

                  {/* Pathology */}
                  {agentSummary.agent_responses?.pathology && (
                    <div className="border rounded-lg p-4">
                      <h4 className="font-semibold text-purple-600 mb-2">Pathology Agent</h4>
                      {agentSummary.agent_responses.pathology.pathology_summary?.pathology_interpretation && (
                        <p className="text-gray-700 text-sm">
                          {agentSummary.agent_responses.pathology.pathology_summary.pathology_interpretation}
                        </p>
                      )}
                      {agentSummary.agent_metadata?.pathology_confidence !== null && (
                        <p className="text-xs text-gray-500 mt-2">
                          Confidence: {agentSummary.agent_metadata.pathology_confidence}
                        </p>
                      )}
                    </div>
                  )}

                  {/* Tumor Board */}
                  {agentSummary.agent_responses?.tumor_board && (
                    <div className="border rounded-lg p-4">
                      <h4 className="font-semibold text-orange-600 mb-2">Tumor Board Agent</h4>
                      {agentSummary.agent_responses.tumor_board.notes_summary?.tumor_board_text && (
                        <p className="text-gray-700 text-sm">
                          {agentSummary.agent_responses.tumor_board.notes_summary.tumor_board_text}
                        </p>
                      )}
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}
        </div>

        {patient.radiology?.studies && patient.radiology.studies.length > 0 && (
          <div className="bg-white rounded-lg shadow p-6">
            <h2 className="text-xl font-semibold mb-4">Radiology Studies</h2>
            <div className="space-y-4">
              {patient.radiology.studies.map((study, idx) => (
                <div key={idx} className="border border-gray-200 rounded-lg p-4">
                  <div className="grid grid-cols-2 gap-4 text-sm mb-3">
                    <div>Date: {study.date || 'N/A'}</div>
                    <div>Modality: {study.modality || 'N/A'}</div>
                    <div>Center: {study.imaging_center || 'N/A'}</div>
                  </div>
                  {study.radiology_report_text && (
                    <p className="text-gray-700 whitespace-pre-wrap text-sm">
                      {study.radiology_report_text}
                    </p>
                  )}
                  {study.files && (study.files.radiology_pdf || study.files.dicom_zip) && (
                    <div className="text-xs text-gray-500 mt-3 space-y-1">
                      {study.files.radiology_pdf && <div>PDF: {study.files.radiology_pdf}</div>}
                      {study.files.dicom_zip && <div>DICOM: {study.files.dicom_zip}</div>}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {patient.pathology && (
          <div className="bg-white rounded-lg shadow p-6">
            <h2 className="text-xl font-semibold mb-4">Pathology</h2>
            <div className="space-y-3 text-sm">
              <div>
                Biopsy performed:{' '}
                {patient.pathology.biopsy_performed === undefined || patient.pathology.biopsy_performed === null
                  ? 'N/A'
                  : patient.pathology.biopsy_performed
                  ? 'Yes'
                  : 'No'}
              </div>
              {patient.pathology.pathology_report_text && (
                <p className="text-gray-700 whitespace-pre-wrap">
                  {patient.pathology.pathology_report_text}
                </p>
              )}
              {patient.pathology.files?.pathology_pdf && (
                <div className="text-xs text-gray-500">
                  Report: {patient.pathology.files.pathology_pdf}
                </div>
              )}
            </div>
          </div>
        )}

        {patient.treatment_history && (
          <div className="bg-white rounded-lg shadow p-6">
            <h2 className="text-xl font-semibold mb-4">Treatment History</h2>
            <div className="space-y-2">
              {patient.treatment_history.previous_treatments &&
                patient.treatment_history.previous_treatments.length > 0 && (
                <div>
                  <span className="text-gray-600">Previous:</span>{' '}
                  <span className="font-medium">
                    {patient.treatment_history.previous_treatments.join(', ')}
                  </span>
                </div>
              )}
              <div>
                <span className="text-gray-600">Current:</span>{' '}
                <span className="font-medium">
                  {patient.treatment_history.current_treatment || 'N/A'}
                </span>
              </div>
              <div>
                <span className="text-gray-600">Response Summary:</span>{' '}
                <span className="font-medium">
                  {patient.treatment_history.treatment_response_notes || 'N/A'}
                </span>
              </div>
            </div>
          </div>
        )}

        {patient.tumor_board && (
          <div className="bg-white rounded-lg shadow p-6">
            <h2 className="text-xl font-semibold mb-4">Tumor Board</h2>
            <div className="space-y-4">
              {patient.tumor_board.tb_notes_text && (
                <div>
                  <p className="text-gray-700 whitespace-pre-wrap">
                    {patient.tumor_board.tb_notes_text}
                  </p>
                </div>
              )}
              {patient.tumor_board.members_present && patient.tumor_board.members_present.length > 0 && (
                <div>
                  <h3 className="font-semibold mb-2">Members Present</h3>
                  <p className="text-gray-700">
                    {patient.tumor_board.members_present.join(', ')}
                  </p>
                </div>
              )}
            </div>
          </div>
        )}

        {patient.ground_truth && (
          <div className="bg-white rounded-lg shadow p-6">
            <h2 className="text-xl font-semibold mb-4">Ground Truth</h2>
            <div className="grid gap-6 md:grid-cols-2">
              {patient.ground_truth.clinical_scores && (
                <div>
                  <h3 className="font-semibold mb-2">Clinical Scores</h3>
                  <div className="grid grid-cols-2 gap-3 text-sm">
                    <div>Child Pugh: {patient.ground_truth.clinical_scores.Child_Pugh || 'N/A'}</div>
                    <div>MELD: {patient.ground_truth.clinical_scores.MELD ?? 'N/A'}</div>
                    <div>MELD-Na: {patient.ground_truth.clinical_scores.MELD_Na ?? 'N/A'}</div>
                    <div>ALBI: {patient.ground_truth.clinical_scores.ALBI || 'N/A'}</div>
                  </div>
                </div>
              )}
              {patient.ground_truth.radiology && (
                <div>
                  <h3 className="font-semibold mb-2">Radiology</h3>
                  <div className="grid grid-cols-2 gap-3 text-sm">
                    <div>LI-RADS: {patient.ground_truth.radiology.true_LIRADS ?? 'N/A'}</div>
                    <div>mRECIST: {patient.ground_truth.radiology.true_mRECIST || 'N/A'}</div>
                    <div className="col-span-2">
                      PVTT: {patient.ground_truth.radiology.true_PVTT ? 'Present' : 'Absent'}
                    </div>
                  </div>
                </div>
              )}
              {patient.ground_truth.pathology && (
                <div>
                  <h3 className="font-semibold mb-2">Pathology</h3>
                  <div className="text-sm space-y-1">
                    <div>Diff: {patient.ground_truth.pathology.true_differentiation || 'N/A'}</div>
                    <div>
                      Vascular Invasion:{' '}
                      {patient.ground_truth.pathology.true_vascular_invasion ? 'Present' : 'Absent'}
                    </div>
                  </div>
                </div>
              )}
              {patient.ground_truth.treatment_staging && (
                <div>
                  <h3 className="font-semibold mb-2">Treatment Staging</h3>
                  <div className="text-sm space-y-1">
                    <div>BCLC: {patient.ground_truth.treatment_staging.true_BCLC || 'N/A'}</div>
                    <div>Intent: {patient.ground_truth.treatment_staging.true_intent || 'N/A'}</div>
                  </div>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}