import { useState, useEffect, useRef } from 'react'
import { Save, Upload, Plus, Trash2, Calendar } from 'lucide-react'

const labFieldConfig = [
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
  { key: 'PIVKA_II_mAU_ml', label: 'PIVKA-II (mAU/mL)' },
]

const modalityOptions = ['CT Triphasic', 'CT with contrast', 'MRI Liver', 'USG']
const sexOptions = ['M', 'F', 'Other']
const ascitesOptions = ['none', 'mild', 'moderate', 'severe']
const encephalopathyOptions = ['none', 'grade1', 'grade2', 'grade3', 'grade4']
const ecogOptions = [0, 1, 2, 3, 4]
const childPughOptions = ['A', 'B', 'C']
const liradsOptions = [1, 2, 3, 4, 5]
const mrecistOptions = ['CR', 'PR', 'SD', 'PD']
const differentiationOptions = ['Well', 'Moderate', 'Poor', 'Undifferentiated']
const bclcOptions = ['0', 'A', 'B', 'C', 'D']
const intentOptions = ['Curative', 'Palliative', 'Downstaging', 'Bridge to transplant']

const createUniqueId = () =>
  typeof crypto !== 'undefined' && crypto.randomUUID
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random()}`

const buildEmptyLabValues = () =>
  labFieldConfig.reduce((acc, field) => {
    acc[field.key] = ''
    return acc
  }, {})

const createEmptyLabEntry = () => ({
  id: createUniqueId(),
  date: '',
  values: buildEmptyLabValues(),
})

const createEmptyRadiologyStudy = () => ({
  id: createUniqueId(),
  date: '',
  modality: '',
  imaging_center: '',
  radiology_report_text: '',
  files: { radiology_pdf: '', dicom_zip: '' },
})

const getInitialFormState = () => ({
  case_id: '',
  demographics: { name: '', age: '', sex: '', BMI: '' },
  clinical: {
    etiology: '',
    symptoms: [],
    comorbidities: [],
    ascites: '',
    encephalopathy: '',
    ECOG: '',
    clinical_notes_text: '',
  },
  lab_data: {
    baseline: buildEmptyLabValues(),
  },
  pathology: {
    biopsy_performed: false,
    pathology_report_text: '',
    files: { pathology_pdf: '' },
  },
  tumor_board: { tb_notes_text: '', members_present: [] },
  treatment_history: {
    previous_treatments: [],
    current_treatment: '',
    treatment_response_notes: '',
  },
  ground_truth: {
    clinical_scores: { Child_Pugh: '', MELD: '', MELD_Na: '', ALBI: '' },
    radiology: { true_LIRADS: '', true_mRECIST: '', true_PVTT: false },
    pathology: { true_differentiation: '', true_vascular_invasion: false },
    treatment_staging: { true_BCLC: '', true_intent: '' },
  },
})

export default function PatientForm({ patient, onSubmit, loading }) {
  const [formData, setFormData] = useState(() => getInitialFormState())
  const [labTimelineEntries, setLabTimelineEntries] = useState([])
  const [radiologyStudies, setRadiologyStudies] = useState([])
  const [symptomInput, setSymptomInput] = useState('')
  const [comorbidityInput, setComorbidityInput] = useState('')
  const [previousTreatmentInput, setPreviousTreatmentInput] = useState('')
  const [boardMemberInput, setBoardMemberInput] = useState('')
  const fileInputRef = useRef(null)

  useEffect(() => {
    if (patient) {
      const base = getInitialFormState()
      const mergedGroundTruth = {
        clinical_scores: {
          ...base.ground_truth.clinical_scores,
          ...(patient.ground_truth?.clinical_scores || {}),
        },
        radiology: {
          ...base.ground_truth.radiology,
          ...(patient.ground_truth?.radiology || {}),
        },
        pathology: {
          ...base.ground_truth.pathology,
          ...(patient.ground_truth?.pathology || {}),
        },
        treatment_staging: {
          ...base.ground_truth.treatment_staging,
          ...(patient.ground_truth?.treatment_staging || {}),
        },
      }

      setFormData({
        case_id: patient.case_id,
        demographics: { ...base.demographics, ...(patient.demographics || {}) },
        clinical: { ...base.clinical, ...(patient.clinical || {}) },
        lab_data: {
          baseline: {
            ...base.lab_data.baseline,
            ...(patient.lab_data?.baseline || {}),
          },
        },
        pathology: { ...base.pathology, ...(patient.pathology || {}) },
        tumor_board: { ...base.tumor_board, ...(patient.tumor_board || {}) },
        treatment_history: {
          ...base.treatment_history,
          ...(patient.treatment_history || {}),
        },
        ground_truth: mergedGroundTruth,
      })

      const timelineEntries = (patient.lab_data?.time_series || []).map((entry) => ({
        id: createUniqueId(),
        date: entry.date || '',
        values: labFieldConfig.reduce((acc, field) => {
          acc[field.key] = entry[field.key] ?? ''
          return acc
        }, buildEmptyLabValues()),
      }))
      setLabTimelineEntries(timelineEntries)

      const studies = (patient.radiology?.studies || []).map((study) => ({
        id: createUniqueId(),
        date: study.date || '',
        modality: study.modality || '',
        imaging_center: study.imaging_center || '',
        radiology_report_text: study.radiology_report_text || '',
        files: {
          radiology_pdf: study.files?.radiology_pdf || '',
          dicom_zip: study.files?.dicom_zip || '',
        },
      }))
      setRadiologyStudies(studies)
    } else {
      setFormData(getInitialFormState())
      setLabTimelineEntries([])
      setRadiologyStudies([])
    }
  }, [patient])

  const handleChange = (path, value) => {
    const keys = path.split('.')
    setFormData((prev) => {
      const newData = { ...prev }
      let current = newData
      for (let i = 0; i < keys.length - 1; i++) {
        current = current[keys[i]] = { ...current[keys[i]] }
      }
      current[keys[keys.length - 1]] = value
      return newData
    })
  }

  const handleArrayAdd = (path, value) => {
    if (!value) return
    const keys = path.split('.')
    setFormData((prev) => {
      const newData = { ...prev }
      let current = newData
      for (let i = 0; i < keys.length - 1; i++) {
        current = current[keys[i]] = { ...current[keys[i]] }
      }
      current[keys[keys.length - 1]] = [...current[keys[keys.length - 1]], value]
      return newData
    })
  }

  const handleArrayRemove = (path, index) => {
    const keys = path.split('.')
    setFormData((prev) => {
      const newData = { ...prev }
      let current = newData
      for (let i = 0; i < keys.length - 1; i++) {
        current = current[keys[i]] = { ...current[keys[i]] }
      }
      current[keys[keys.length - 1]] = current[keys[keys.length - 1]].filter((_, i) => i !== index)
      return newData
    })
  }

  const addLabTimelineEntry = () => {
    setLabTimelineEntries((entries) => [
      ...entries,
      { ...createEmptyLabEntry(), date: new Date().toISOString().split('T')[0] },
    ])
  }

  const removeLabTimelineEntry = (index) => {
    setLabTimelineEntries((entries) => entries.filter((_, i) => i !== index))
  }

  const updateLabTimelineEntry = (index, field, value) => {
    setLabTimelineEntries((entries) => {
      const updated = [...entries]
      const entry = { ...updated[index], values: { ...updated[index].values } }
      if (field === 'date') {
        entry.date = value
      } else {
        entry.values[field] = value === '' ? '' : value
      }
      updated[index] = entry
      return updated
    })
  }

  const addRadiologyStudy = () => {
    setRadiologyStudies((prev) => [...prev, createEmptyRadiologyStudy()])
  }

  const removeRadiologyStudy = (index) => {
    setRadiologyStudies((prev) => prev.filter((_, i) => i !== index))
  }

  const updateRadiologyStudy = (index, path, value) => {
    setRadiologyStudies((prev) => {
      const updated = [...prev]
      const keys = path.split('.')
      const study = { ...updated[index], files: { ...updated[index].files } }
      let current = study
      for (let i = 0; i < keys.length - 1; i++) {
        current[keys[i]] = { ...current[keys[i]] }
        current = current[keys[i]]
      }
      current[keys[keys.length - 1]] = value
      updated[index] = study
      return updated
    })
  }

  const handleFileUpload = (e) => {
    const file = e.target.files?.[0]
    if (!file) return

    const reader = new FileReader()
    reader.onload = (event) => {
      try {
        const jsonData = JSON.parse(event.target.result)
        const base = getInitialFormState()

        setFormData({
          case_id: jsonData.case_id || '',
          demographics: { ...base.demographics, ...(jsonData.demographics || {}) },
          clinical: { ...base.clinical, ...(jsonData.clinical || {}) },
          lab_data: {
            baseline: {
              ...base.lab_data.baseline,
              ...(jsonData.lab_data?.baseline || {}),
            },
          },
          pathology: { ...base.pathology, ...(jsonData.pathology || {}) },
          tumor_board: { ...base.tumor_board, ...(jsonData.tumor_board || {}) },
          treatment_history: {
            ...base.treatment_history,
            ...(jsonData.treatment_history || {}),
          },
          ground_truth: {
            clinical_scores: {
              ...base.ground_truth.clinical_scores,
              ...(jsonData.ground_truth?.clinical_scores || {}),
            },
            radiology: {
              ...base.ground_truth.radiology,
              ...(jsonData.ground_truth?.radiology || {}),
            },
            pathology: {
              ...base.ground_truth.pathology,
              ...(jsonData.ground_truth?.pathology || {}),
            },
            treatment_staging: {
              ...base.ground_truth.treatment_staging,
              ...(jsonData.ground_truth?.treatment_staging || {}),
            },
          },
        })

        setLabTimelineEntries(
          (jsonData.lab_data?.time_series || []).map((entry) => ({
            id: createUniqueId(),
            date: entry.date || '',
            values: labFieldConfig.reduce((acc, field) => {
              acc[field.key] = entry[field.key] ?? ''
              return acc
            }, buildEmptyLabValues()),
          }))
        )

        setRadiologyStudies(
          (jsonData.radiology?.studies || []).map((study) => ({
            id: createUniqueId(),
            date: study.date || '',
            modality: study.modality || '',
            imaging_center: study.imaging_center || '',
            radiology_report_text: study.radiology_report_text || '',
            files: {
              radiology_pdf: study.files?.radiology_pdf || '',
              dicom_zip: study.files?.dicom_zip || '',
            },
          }))
        )

        alert('Form filled successfully from JSON file!')
      } catch (error) {
        console.error('Error parsing JSON file:', error)
        alert('Error parsing JSON file. Please check the file format.')
      }
    }
    reader.onerror = () => {
      alert('Error reading file. Please try again.')
    }
    reader.readAsText(file)

    if (fileInputRef.current) {
      fileInputRef.current.value = ''
    }
  }

  const numericKeys = new Set(['age', 'BMI', 'ECOG', 'MELD', 'MELD_Na'])
  const booleanKeys = new Set(['biopsy_performed', 'true_PVTT', 'true_vascular_invasion'])

  const cleanObject = (obj) => {
    if (!obj || typeof obj !== 'object') return null
    const cleaned = {}

    Object.entries(obj).forEach(([key, value]) => {
      if (booleanKeys.has(key)) {
        cleaned[key] = Boolean(value)
        return
      }

      if (numericKeys.has(key)) {
        if (value === '' || value === null || value === undefined) return
        const num = typeof value === 'number' ? value : parseFloat(value)
        if (!Number.isNaN(num)) {
          cleaned[key] = num
        }
        return
      }

      if (Array.isArray(value)) {
        const filtered = value.filter((item) => item !== '' && item !== null && item !== undefined)
        if (filtered.length > 0) {
          cleaned[key] = filtered
        }
        return
      }

      if (value && typeof value === 'object') {
        const nested = cleanObject(value)
        if (nested && Object.keys(nested).length > 0) {
          cleaned[key] = nested
        }
        return
      }

      if (value !== '' && value !== null && value !== undefined) {
        cleaned[key] = value
      }
    })

    return Object.keys(cleaned).length > 0 ? cleaned : null
  }

  const cleanFormData = (data) => {
    const cleanedBaseline = {}
    labFieldConfig.forEach(({ key }) => {
      const value = data.lab_data?.baseline?.[key]
      if (value !== '' && value !== null && value !== undefined) {
        const num = typeof value === 'number' ? value : parseFloat(value)
        if (!Number.isNaN(num)) {
          cleanedBaseline[key] = num
        }
      }
    })

    const cleanedTimeSeries = labTimelineEntries
      .filter(
        (entry) =>
          entry.date &&
          Object.values(entry.values).some((val) => val !== '' && val !== null && val !== undefined)
      )
      .map((entry) => {
        const measurements = {}
        labFieldConfig.forEach(({ key }) => {
          const value = entry.values[key]
          if (value !== '' && value !== null && value !== undefined) {
            const num = typeof value === 'number' ? value : parseFloat(value)
            if (!Number.isNaN(num)) {
              measurements[key] = num
            }
          }
        })
        return { date: entry.date, ...measurements }
      })

    const labPayload = {}
    if (Object.keys(cleanedBaseline).length > 0) {
      labPayload.baseline = cleanedBaseline
    }
    if (cleanedTimeSeries.length > 0) {
      labPayload.time_series = cleanedTimeSeries
    }

    const radiologyPayload = radiologyStudies
      .map((study) => {
        const cleanedStudy = {}
        if (study.date) cleanedStudy.date = study.date
        if (study.modality) cleanedStudy.modality = study.modality
        if (study.imaging_center) cleanedStudy.imaging_center = study.imaging_center
        if (study.radiology_report_text) cleanedStudy.radiology_report_text = study.radiology_report_text
        const files = {}
        if (study.files?.radiology_pdf) files.radiology_pdf = study.files.radiology_pdf
        if (study.files?.dicom_zip) files.dicom_zip = study.files.dicom_zip
        if (Object.keys(files).length > 0) {
          cleanedStudy.files = files
        }
        return cleanedStudy
      })
      .filter((study) => Object.keys(study).length > 0)

    const payload = {
      case_id: data.case_id,
      demographics: cleanObject(data.demographics),
      clinical: cleanObject(data.clinical),
      lab_data: Object.keys(labPayload).length > 0 ? labPayload : undefined,
      radiology: radiologyPayload.length > 0 ? { studies: radiologyPayload } : undefined,
      pathology: cleanObject(data.pathology),
      tumor_board: cleanObject(data.tumor_board),
      treatment_history: cleanObject(data.treatment_history),
      ground_truth: cleanObject(data.ground_truth),
    }

    Object.keys(payload).forEach((key) => {
      if (payload[key] === null || payload[key] === undefined) {
        delete payload[key]
      }
    })

    return payload
  }

  const handleSubmit = (e) => {
    e.preventDefault()
    const cleanedData = cleanFormData(formData)
    onSubmit(cleanedData)
  }

  return (
    <form onSubmit={handleSubmit} className="bg-white rounded-lg shadow p-6 space-y-6">
      {!patient && (
        <div className="mb-4 p-4 bg-blue-50 border border-blue-200 rounded-lg">
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Upload JSON File to Auto-fill Form
          </label>
          <div className="flex items-center gap-4">
            <input
              ref={fileInputRef}
              type="file"
              accept=".json"
              onChange={handleFileUpload}
              className="hidden"
              id="json-upload"
            />
            <label
              htmlFor="json-upload"
              className="flex items-center px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 cursor-pointer transition-colors"
            >
              <Upload className="h-5 w-5 mr-2" />
              Choose JSON File
            </label>
            <span className="text-sm text-gray-600">
              Upload a JSON file to automatically populate all form fields
            </span>
          </div>
        </div>
      )}

      {!patient && (
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Case ID <span className="text-red-500">*</span>
          </label>
          <input
            type="text"
            required
            value={formData.case_id}
            onChange={(e) => handleChange('case_id', e.target.value)}
            className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
            placeholder="TB-2025-0012"
          />
        </div>
      )}

      <div className="border-t pt-6">
        <h3 className="text-lg font-semibold mb-4">Demographics</h3>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Name</label>
            <input
              type="text"
              value={formData.demographics.name}
              onChange={(e) => handleChange('demographics.name', e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-md"
              placeholder="John Doe"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Age</label>
            <input
              type="number"
              value={formData.demographics.age}
              onChange={(e) => handleChange('demographics.age', e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-md"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Sex</label>
            <select
              value={formData.demographics.sex}
              onChange={(e) => handleChange('demographics.sex', e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-md"
            >
              <option value="">Select</option>
              {sexOptions.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">BMI</label>
            <input
              type="number"
              step="0.1"
              value={formData.demographics.BMI}
              onChange={(e) => handleChange('demographics.BMI', e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-md"
            />
          </div>
        </div>
      </div>

      <div className="border-t pt-6">
        <h3 className="text-lg font-semibold mb-4">Clinical</h3>
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Etiology</label>
            <input
              type="text"
              value={formData.clinical.etiology}
              onChange={(e) => handleChange('clinical.etiology', e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-md"
              placeholder="HCV-related cirrhosis"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Symptoms</label>
            <div className="flex gap-2 mb-2">
              <input
                type="text"
                value={symptomInput}
                onChange={(e) => setSymptomInput(e.target.value)}
                onKeyPress={(e) => {
                  if (e.key === 'Enter' && symptomInput) {
                    e.preventDefault()
                    handleArrayAdd('clinical.symptoms', symptomInput)
                    setSymptomInput('')
                  }
                }}
                className="flex-1 px-3 py-2 border border-gray-300 rounded-md"
                placeholder="Add symptom and press Enter"
              />
            </div>
            <div className="flex flex-wrap gap-2">
              {formData.clinical.symptoms.map((symptom, idx) => (
                <span
                  key={idx}
                  className="inline-flex items-center px-3 py-1 bg-blue-100 text-blue-800 rounded-full text-sm"
                >
                  {symptom}
                  <button
                    type="button"
                    onClick={() => handleArrayRemove('clinical.symptoms', idx)}
                    className="ml-2 text-blue-600 hover:text-blue-800"
                  >
                    ×
                  </button>
                </span>
              ))}
            </div>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Comorbidities</label>
            <div className="flex gap-2 mb-2">
              <input
                type="text"
                value={comorbidityInput}
                onChange={(e) => setComorbidityInput(e.target.value)}
                onKeyPress={(e) => {
                  if (e.key === 'Enter' && comorbidityInput) {
                    e.preventDefault()
                    handleArrayAdd('clinical.comorbidities', comorbidityInput)
                    setComorbidityInput('')
                  }
                }}
                className="flex-1 px-3 py-2 border border-gray-300 rounded-md"
                placeholder="Add comorbidity and press Enter"
              />
            </div>
            <div className="flex flex-wrap gap-2">
              {formData.clinical.comorbidities.map((comorbidity, idx) => (
                <span
                  key={idx}
                  className="inline-flex items-center px-3 py-1 bg-green-100 text-green-800 rounded-full text-sm"
                >
                  {comorbidity}
                  <button
                    type="button"
                    onClick={() => handleArrayRemove('clinical.comorbidities', idx)}
                    className="ml-2 text-green-600 hover:text-green-800"
                  >
                    ×
                  </button>
                </span>
              ))}
            </div>
          </div>
          <div className="grid grid-cols-3 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Ascites</label>
              <select
                value={formData.clinical.ascites}
                onChange={(e) => handleChange('clinical.ascites', e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 rounded-md"
              >
                <option value="">Select</option>
                {ascitesOptions.map((option) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Encephalopathy</label>
              <select
                value={formData.clinical.encephalopathy}
                onChange={(e) => handleChange('clinical.encephalopathy', e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 rounded-md"
              >
                <option value="">Select</option>
                {encephalopathyOptions.map((option) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">ECOG</label>
              <select
                value={formData.clinical.ECOG}
                onChange={(e) => handleChange('clinical.ECOG', e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 rounded-md"
              >
                <option value="">Select</option>
                {ecogOptions.map((option) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
              </select>
            </div>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Clinical Notes</label>
            <textarea
              value={formData.clinical.clinical_notes_text}
              onChange={(e) => handleChange('clinical.clinical_notes_text', e.target.value)}
              rows="4"
              className="w-full px-3 py-2 border border-gray-300 rounded-md"
              placeholder="Patient reports fatigue and anorexia..."
            />
          </div>
        </div>
      </div>

      <div className="border-t pt-6">
        <h3 className="text-lg font-semibold mb-4">Lab Data - Baseline</h3>
        <div className="grid grid-cols-3 gap-4">
          {labFieldConfig.map(({ key, label }) => (
            <div key={key}>
              <label className="block text-sm font-medium text-gray-700 mb-1">{label}</label>
              <input
                type="number"
                step="0.01"
                value={formData.lab_data.baseline[key]}
                onChange={(e) => handleChange(`lab_data.baseline.${key}`, e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 rounded-md"
              />
            </div>
          ))}
        </div>
      </div>

      <div className="border-t pt-6">
        <div className="flex justify-between items-center mb-4">
          <h3 className="text-lg font-semibold flex items-center">
            <Calendar className="h-5 w-5 mr-2 text-blue-600" />
            Lab Data Timeline
          </h3>
          <button
            type="button"
            onClick={addLabTimelineEntry}
            className="flex items-center px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
          >
            <Plus className="h-4 w-4 mr-2" />
            Add Lab Results
          </button>
        </div>

        {labTimelineEntries.length === 0 ? (
          <p className="text-gray-500 text-sm italic">
            No timeline entries added yet. Click "Add Lab Results" to add follow-up lab values.
          </p>
        ) : (
          <div className="space-y-4">
            {[...labTimelineEntries]
              .sort((a, b) => new Date(a.date) - new Date(b.date))
              .map((entry) => {
                const originalIndex = labTimelineEntries.findIndex((e) => e.id === entry.id)
                return (
                  <div key={entry.id} className="border border-gray-200 rounded-lg p-4 bg-gray-50">
                    <div className="flex justify-between items-start mb-3">
                      <div className="flex items-center gap-2">
                        <Calendar className="h-4 w-4 text-gray-500" />
                        <label className="text-sm font-medium text-gray-700">Date:</label>
                        <input
                          type="date"
                          value={entry.date}
                          onChange={(e) => updateLabTimelineEntry(originalIndex, 'date', e.target.value)}
                          className="px-2 py-1 border border-gray-300 rounded-md text-sm"
                        />
                      </div>
                      <button
                        type="button"
                        onClick={() => removeLabTimelineEntry(originalIndex)}
                        className="flex items-center px-2 py-1 text-red-600 hover:bg-red-50 rounded transition-colors"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </div>
                    <div className="grid grid-cols-3 gap-3">
                      {labFieldConfig.map(({ key, label }) => (
                        <div key={key}>
                          <label className="block text-xs font-medium text-gray-600 mb-1">{label}</label>
                          <input
                            type="number"
                            step="0.01"
                            value={entry.values[key]}
                            onChange={(e) => updateLabTimelineEntry(originalIndex, key, e.target.value)}
                            className="w-full px-2 py-1 border border-gray-300 rounded-md text-sm"
                            placeholder="0.00"
                          />
                        </div>
                      ))}
                    </div>
                  </div>
                )
              })}
          </div>
        )}
      </div>

      <div className="border-t pt-6">
        <div className="flex justify-between items-center mb-4">
          <h3 className="text-lg font-semibold">Radiology Studies</h3>
          <button
            type="button"
            onClick={addRadiologyStudy}
            className="flex items-center px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
          >
            <Plus className="h-4 w-4 mr-2" />
            Add Study
          </button>
        </div>
        {radiologyStudies.length === 0 ? (
          <p className="text-gray-500 text-sm italic">No studies recorded yet.</p>
        ) : (
          <div className="space-y-4">
            {radiologyStudies.map((study, index) => (
              <div key={study.id} className="border border-gray-200 rounded-lg p-4 bg-gray-50">
                <div className="flex justify-between items-start mb-3">
                  <div className="grid grid-cols-3 gap-4 flex-1">
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">Date</label>
                      <input
                        type="date"
                        value={study.date}
                        onChange={(e) => updateRadiologyStudy(index, 'date', e.target.value)}
                        className="w-full px-3 py-2 border border-gray-300 rounded-md"
                      />
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">Modality</label>
                      <select
                        value={study.modality}
                        onChange={(e) => updateRadiologyStudy(index, 'modality', e.target.value)}
                        className="w-full px-3 py-2 border border-gray-300 rounded-md"
                      >
                        <option value="">Select</option>
                        {modalityOptions.map((option) => (
                          <option key={option} value={option}>
                            {option}
                          </option>
                        ))}
                      </select>
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">Imaging Center</label>
                      <input
                        type="text"
                        value={study.imaging_center}
                        onChange={(e) => updateRadiologyStudy(index, 'imaging_center', e.target.value)}
                        className="w-full px-3 py-2 border border-gray-300 rounded-md"
                        placeholder="Apollo Radiology"
                      />
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() => removeRadiologyStudy(index)}
                    className="flex items-center px-2 py-1 text-red-600 hover:bg-red-50 rounded transition-colors ml-4"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
                <div className="space-y-3">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Radiology Report</label>
                    <textarea
                      rows="4"
                      value={study.radiology_report_text}
                      onChange={(e) => updateRadiologyStudy(index, 'radiology_report_text', e.target.value)}
                      className="w-full px-3 py-2 border border-gray-300 rounded-md"
                      placeholder="Summary of findings..."
                    />
                  </div>
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">Radiology PDF</label>
                      <input
                        type="text"
                        value={study.files.radiology_pdf}
                        onChange={(e) => updateRadiologyStudy(index, 'files.radiology_pdf', e.target.value)}
                        className="w-full px-3 py-2 border border-gray-300 rounded-md"
                        placeholder="Path or filename"
                      />
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">DICOM ZIP</label>
                      <input
                        type="text"
                        value={study.files.dicom_zip}
                        onChange={(e) => updateRadiologyStudy(index, 'files.dicom_zip', e.target.value)}
                        className="w-full px-3 py-2 border border-gray-300 rounded-md"
                        placeholder="Path or filename"
                      />
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="border-t pt-6">
        <h3 className="text-lg font-semibold mb-4">Pathology</h3>
        <div className="space-y-4">
          <label className="inline-flex items-center gap-2 text-sm font-medium text-gray-700">
            <input
              type="checkbox"
              checked={formData.pathology.biopsy_performed}
              onChange={(e) => handleChange('pathology.biopsy_performed', e.target.checked)}
              className="h-4 w-4 text-blue-600 border-gray-300 rounded"
            />
            Biopsy performed
          </label>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Pathology Report</label>
            <textarea
              rows="4"
              value={formData.pathology.pathology_report_text}
              onChange={(e) => handleChange('pathology.pathology_report_text', e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-md"
              placeholder="Moderately differentiated HCC..."
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Pathology PDF</label>
            <input
              type="text"
              value={formData.pathology.files.pathology_pdf}
              onChange={(e) => handleChange('pathology.files.pathology_pdf', e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-md"
              placeholder="Path or filename"
            />
          </div>
        </div>
      </div>

      <div className="border-t pt-6">
        <h3 className="text-lg font-semibold mb-4">Treatment History</h3>
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Previous Treatments</label>
            <div className="flex gap-2 mb-2">
              <input
                type="text"
                value={previousTreatmentInput}
                onChange={(e) => setPreviousTreatmentInput(e.target.value)}
                onKeyPress={(e) => {
                  if (e.key === 'Enter' && previousTreatmentInput) {
                    e.preventDefault()
                    handleArrayAdd('treatment_history.previous_treatments', previousTreatmentInput)
                    setPreviousTreatmentInput('')
                  }
                }}
                className="flex-1 px-3 py-2 border border-gray-300 rounded-md"
                placeholder="e.g., TACE, RFA"
              />
            </div>
            <div className="flex flex-wrap gap-2">
              {formData.treatment_history.previous_treatments.map((treatment, idx) => (
                <span
                  key={idx}
                  className="inline-flex items-center px-3 py-1 bg-yellow-100 text-yellow-800 rounded-full text-sm"
                >
                  {treatment}
                  <button
                    type="button"
                    onClick={() => handleArrayRemove('treatment_history.previous_treatments', idx)}
                    className="ml-2 text-yellow-600 hover:text-yellow-800"
                  >
                    ×
                  </button>
                </span>
              ))}
            </div>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Current Treatment</label>
            <input
              type="text"
              value={formData.treatment_history.current_treatment}
              onChange={(e) => handleChange('treatment_history.current_treatment', e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-md"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Response Summary</label>
            <textarea
              value={formData.treatment_history.treatment_response_notes}
              onChange={(e) => handleChange('treatment_history.treatment_response_notes', e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-md"
              rows="3"
            />
          </div>
        </div>
      </div>

      <div className="border-t pt-6">
        <h3 className="text-lg font-semibold mb-4">Tumor Board</h3>
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Notes</label>
            <textarea
              value={formData.tumor_board.tb_notes_text}
              onChange={(e) => handleChange('tumor_board.tb_notes_text', e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-md"
              rows="4"
              placeholder="Patient discussed in multidisciplinary tumor board..."
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Members Present</label>
            <div className="flex gap-2 mb-2">
              <input
                type="text"
                value={boardMemberInput}
                onChange={(e) => setBoardMemberInput(e.target.value)}
                onKeyPress={(e) => {
                  if (e.key === 'Enter' && boardMemberInput) {
                    e.preventDefault()
                    handleArrayAdd('tumor_board.members_present', boardMemberInput)
                    setBoardMemberInput('')
                  }
                }}
                className="flex-1 px-3 py-2 border border-gray-300 rounded-md"
                placeholder="e.g., Hepatologist"
              />
            </div>
            <div className="flex flex-wrap gap-2">
              {formData.tumor_board.members_present.map((member, idx) => (
                <span
                  key={idx}
                  className="inline-flex items-center px-3 py-1 bg-purple-100 text-purple-800 rounded-full text-sm"
                >
                  {member}
                  <button
                    type="button"
                    onClick={() => handleArrayRemove('tumor_board.members_present', idx)}
                    className="ml-2 text-purple-600 hover:text-purple-800"
                  >
                    ×
                  </button>
                </span>
              ))}
            </div>
          </div>
        </div>
      </div>

      <div className="border-t pt-6">
        <h3 className="text-lg font-semibold mb-4">Ground Truth</h3>
        <div className="grid gap-6 md:grid-cols-2">
          <div className="space-y-3">
            <h4 className="font-semibold">Clinical Scores</h4>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-sm text-gray-600 mb-1">Child Pugh</label>
                <select
                  value={formData.ground_truth.clinical_scores.Child_Pugh}
                  onChange={(e) => handleChange('ground_truth.clinical_scores.Child_Pugh', e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md"
                >
                  <option value="">Select</option>
                  {childPughOptions.map((option) => (
                    <option key={option} value={option}>
                      {option}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-sm text-gray-600 mb-1">MELD</label>
                <input
                  type="number"
                  value={formData.ground_truth.clinical_scores.MELD}
                  onChange={(e) => handleChange('ground_truth.clinical_scores.MELD', e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md"
                />
              </div>
              <div>
                <label className="block text-sm text-gray-600 mb-1">MELD-Na</label>
                <input
                  type="number"
                  value={formData.ground_truth.clinical_scores.MELD_Na}
                  onChange={(e) => handleChange('ground_truth.clinical_scores.MELD_Na', e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md"
                />
              </div>
              <div>
                <label className="block text-sm text-gray-600 mb-1">ALBI</label>
                <input
                  type="text"
                  value={formData.ground_truth.clinical_scores.ALBI}
                  onChange={(e) => handleChange('ground_truth.clinical_scores.ALBI', e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md"
                />
              </div>
            </div>
          </div>
          <div className="space-y-3">
            <h4 className="font-semibold">Radiology Truth</h4>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-sm text-gray-600 mb-1">LI-RADS</label>
                <select
                  value={formData.ground_truth.radiology.true_LIRADS}
                  onChange={(e) => handleChange('ground_truth.radiology.true_LIRADS', e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md"
                >
                  <option value="">Select</option>
                  {liradsOptions.map((option) => (
                    <option key={option} value={option}>
                      {option}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-sm text-gray-600 mb-1">mRECIST</label>
                <select
                  value={formData.ground_truth.radiology.true_mRECIST}
                  onChange={(e) => handleChange('ground_truth.radiology.true_mRECIST', e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md"
                >
                  <option value="">Select</option>
                  {mrecistOptions.map((option) => (
                    <option key={option} value={option}>
                      {option}
                    </option>
                  ))}
                </select>
              </div>
              <label className="inline-flex items-center gap-2 text-sm font-medium text-gray-700 col-span-2">
                <input
                  type="checkbox"
                  checked={formData.ground_truth.radiology.true_PVTT}
                  onChange={(e) => handleChange('ground_truth.radiology.true_PVTT', e.target.checked)}
                  className="h-4 w-4 text-blue-600 border-gray-300 rounded"
                />
                Portal vein tumor thrombosis present
              </label>
            </div>
          </div>
          <div className="space-y-3">
            <h4 className="font-semibold">Pathology Truth</h4>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-sm text-gray-600 mb-1">Differentiation</label>
                <select
                  value={formData.ground_truth.pathology.true_differentiation}
                  onChange={(e) => handleChange('ground_truth.pathology.true_differentiation', e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md"
                >
                  <option value="">Select</option>
                  {differentiationOptions.map((option) => (
                    <option key={option} value={option}>
                      {option}
                    </option>
                  ))}
                </select>
              </div>
              <label className="inline-flex items-center gap-2 text-sm font-medium text-gray-700">
                <input
                  type="checkbox"
                  checked={formData.ground_truth.pathology.true_vascular_invasion}
                  onChange={(e) => handleChange('ground_truth.pathology.true_vascular_invasion', e.target.checked)}
                  className="h-4 w-4 text-blue-600 border-gray-300 rounded"
                />
                Vascular invasion present
              </label>
            </div>
          </div>
          <div className="space-y-3">
            <h4 className="font-semibold">Treatment Staging</h4>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-sm text-gray-600 mb-1">BCLC</label>
                <select
                  value={formData.ground_truth.treatment_staging.true_BCLC}
                  onChange={(e) => handleChange('ground_truth.treatment_staging.true_BCLC', e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md"
                >
                  <option value="">Select</option>
                  {bclcOptions.map((option) => (
                    <option key={option} value={option}>
                      {option}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-sm text-gray-600 mb-1">Intent</label>
                <select
                  value={formData.ground_truth.treatment_staging.true_intent}
                  onChange={(e) => handleChange('ground_truth.treatment_staging.true_intent', e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md"
                >
                  <option value="">Select</option>
                  {intentOptions.map((option) => (
                    <option key={option} value={option}>
                      {option}
                    </option>
                  ))}
                </select>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="flex justify-end pt-6 border-t">
        <button
          type="submit"
          disabled={loading}
          className="flex items-center px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
        >
          <Save className="h-5 w-5 mr-2" />
          {loading ? 'Saving...' : 'Save Patient'}
        </button>
      </div>
    </form>
  )
}

