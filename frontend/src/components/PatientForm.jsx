import { useState, useEffect, useRef } from 'react'
import { Save, Upload, Plus, Trash2, Calendar } from 'lucide-react'

export default function PatientForm({ patient, onSubmit, loading }) {
  const [formData, setFormData] = useState({
    case_id: '',
    demographics: { name: '', age: '', sex: '' },
    clinical_summary: { etiology: '', symptoms: [], comorbidities: [] },
    lab_data: { 
      baseline: { ALT: '', AST: '', Tbil: '', Alb: '', PT: '', INR: '' },
      derived_scores: { CTP: '', MELD_Na: '', AFP: '' }
    },
    imaging: { modality: '', findings: [{ lesion_count: '', largest_size_cm: '', segment: '', LIRADS: '', PVTT: false }] },
    histopathology: { biopsy: '', fibrosis_stage: '' },
    treatment_history: { previous: [], current: '', response_summary: '' },
    tumor_board_notes: { discussion: '', recommendation: '', board_members: [] }
  })

  const [symptomInput, setSymptomInput] = useState('')
  const [comorbidityInput, setComorbidityInput] = useState('')
  const [previousTreatmentInput, setPreviousTreatmentInput] = useState('')
  const [boardMemberInput, setBoardMemberInput] = useState('')
  const fileInputRef = useRef(null)
  
  // Lab timeline entries - stored as array of {date, values}
  const [labTimelineEntries, setLabTimelineEntries] = useState([])

  useEffect(() => {
    if (patient) {
      const labData = patient.lab_data || formData.lab_data
      
      // Extract timeline entries from lab_data (dates that aren't baseline or derived_scores)
      const timelineEntries = []
      if (labData) {
        Object.keys(labData).forEach(key => {
          if (key !== 'baseline' && key !== 'derived_scores' && key !== 'follow_up') {
            timelineEntries.push({
              id: Date.now() + Math.random(), // Unique ID
              date: key,
              values: labData[key]
            })
          }
        })
        // Sort by date
        timelineEntries.sort((a, b) => new Date(a.date) - new Date(b.date))
      }
      
      setFormData({
        case_id: patient.case_id,
        demographics: patient.demographics || formData.demographics,
        clinical_summary: patient.clinical_summary || formData.clinical_summary,
        lab_data: labData,
        imaging: patient.imaging || formData.imaging,
        histopathology: patient.histopathology || formData.histopathology,
        treatment_history: patient.treatment_history || formData.treatment_history,
        tumor_board_notes: patient.tumor_board_notes || formData.tumor_board_notes
      })
      setLabTimelineEntries(timelineEntries)
    }
  }, [patient])

  const handleChange = (path, value) => {
    const keys = path.split('.')
    setFormData(prev => {
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
    const keys = path.split('.')
    setFormData(prev => {
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
    setFormData(prev => {
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
    const today = new Date().toISOString().split('T')[0]
    const newEntry = {
      id: Date.now() + Math.random(), // Unique ID
      date: today,
      values: { ALT: '', AST: '', Tbil: '', Alb: '', PT: '', INR: '' }
    }
    setLabTimelineEntries([...labTimelineEntries, newEntry])
  }

  const removeLabTimelineEntry = (index) => {
    setLabTimelineEntries(labTimelineEntries.filter((_, i) => i !== index))
  }

  const updateLabTimelineEntry = (index, field, value) => {
    const updated = [...labTimelineEntries]
    if (field === 'date') {
      updated[index].date = value
    } else {
      updated[index].values[field] = value === '' ? '' : parseFloat(value) || ''
    }
    setLabTimelineEntries(updated)
  }

  const cleanFormData = (data) => {
    const clean = (value) => {
      // Handle empty strings, null, undefined
      if (value === '' || value === null || value === undefined) {
        return null
      }
      
      // Handle arrays - filter out empty items
      if (Array.isArray(value)) {
        const filtered = value.filter(item => item !== '' && item !== null && item !== undefined)
        return filtered.length > 0 ? filtered : []
      }
      
      // Handle objects
      if (typeof value === 'object' && value !== null && !Array.isArray(value)) {
        const cleaned = {}
        
        // Known numeric fields that should be integers
        const intFields = ['age', 'fibrosis_stage', 'lesion_count', 'segment', 'LIRADS', 'ECOG']
        // Known numeric fields that should be floats
        const floatFields = ['largest_size_cm']
        
        for (const [key, val] of Object.entries(value)) {
          // Skip empty values
          if (val === '' || val === null || val === undefined) {
            continue
          }
          
          let cleanedVal = null
          
          // Handle known integer fields
          if (intFields.includes(key)) {
            const num = typeof val === 'string' ? parseInt(val, 10) : val
            if (!isNaN(num) && num !== '') {
              cleanedVal = num
            }
          }
          // Handle known float fields
          else if (floatFields.includes(key)) {
            const num = typeof val === 'string' ? parseFloat(val) : val
            if (!isNaN(num) && num !== '') {
              cleanedVal = num
            }
          }
          // Handle arrays - recursively clean
          else if (Array.isArray(val)) {
            cleanedVal = clean(val)
            if (cleanedVal !== null && cleanedVal.length > 0) {
              cleaned[key] = cleanedVal
            }
          }
          // Handle nested objects - recursively clean
          else if (typeof val === 'object' && val !== null) {
            cleanedVal = clean(val)
            if (cleanedVal !== null && Object.keys(cleanedVal).length > 0) {
              cleaned[key] = cleanedVal
            }
          }
          // Handle primitive values (strings, numbers, booleans)
          else {
            // Check if it's a numeric string that should be converted (for lab_data values)
            if (typeof val === 'string' && val.trim() !== '' && !isNaN(val)) {
              cleanedVal = val.includes('.') ? parseFloat(val) : parseInt(val, 10)
            } else {
              cleanedVal = val
            }
            if (cleanedVal !== null && cleanedVal !== undefined && cleanedVal !== '') {
              cleaned[key] = cleanedVal
            }
          }
        }
        
        return Object.keys(cleaned).length > 0 ? cleaned : null
      }
      
      return value
    }

    // Merge timeline entries into lab_data
    const labDataWithTimeline = { ...data.lab_data }
    labTimelineEntries.forEach(entry => {
      if (entry.date && entry.values) {
        // Only add if there's at least one non-empty value
        const hasValues = Object.values(entry.values).some(v => v !== '' && v !== null && v !== undefined)
        if (hasValues) {
          labDataWithTimeline[entry.date] = clean(entry.values)
        }
      }
    })

    const cleaned = {
      case_id: data.case_id,
      demographics: clean(data.demographics),
      clinical_summary: clean(data.clinical_summary),
      lab_data: clean(labDataWithTimeline),
      imaging: clean(data.imaging),
      histopathology: clean(data.histopathology),
      treatment_history: clean(data.treatment_history),
      tumor_board_notes: clean(data.tumor_board_notes)
    }

    // Remove null values at the top level (but keep case_id)
    Object.keys(cleaned).forEach(key => {
      if (key !== 'case_id' && cleaned[key] === null) {
        delete cleaned[key]
      }
    })

    return cleaned
  }

  const handleFileUpload = (e) => {
    const file = e.target.files?.[0]
    if (!file) return

    const reader = new FileReader()
    reader.onload = (event) => {
      try {
        const jsonData = JSON.parse(event.target.result)
        
        // Convert the JSON data to form format
        const convertedData = {
          case_id: jsonData.case_id || '',
          demographics: {
            name: jsonData.demographics?.name || '',
            age: jsonData.demographics?.age || '',
            sex: jsonData.demographics?.sex || ''
          },
          clinical_summary: {
            etiology: jsonData.clinical_summary?.etiology || '',
            symptoms: jsonData.clinical_summary?.symptoms || [],
            comorbidities: jsonData.clinical_summary?.comorbidities || []
          },
          lab_data: {
            baseline: jsonData.lab_data?.baseline || { ALT: '', AST: '', Tbil: '', Alb: '', PT: '', INR: '' },
            follow_up: jsonData.lab_data?.follow_up || {},
            derived_scores: jsonData.lab_data?.derived_scores || { CTP: '', MELD_Na: '', AFP: '' }
          },
          imaging: {
            modality: jsonData.imaging?.modality || '',
            findings: jsonData.imaging?.findings?.length > 0 
              ? jsonData.imaging.findings.map(f => ({
                  date: f.date || '',
                  lesion_count: f.lesion_count || '',
                  largest_size_cm: f.largest_size_cm || '',
                  segment: f.segment || '',
                  LIRADS: f.LIRADS || '',
                  PVTT: f.PVTT || false,
                  METS: f.METS || '',
                  ECOG: f.ECOG || ''
                }))
              : [{ lesion_count: '', largest_size_cm: '', segment: '', LIRADS: '', PVTT: false }],
            follow_up_findings: jsonData.imaging?.follow_up_findings || {},
            attachments: jsonData.imaging?.attachments || []
          },
          histopathology: {
            biopsy: jsonData.histopathology?.biopsy || '',
            fibrosis_stage: jsonData.histopathology?.fibrosis_stage || '',
            comments: jsonData.histopathology?.comments || ''
          },
          treatment_history: {
            previous: jsonData.treatment_history?.previous || [],
            current: jsonData.treatment_history?.current || '',
            response_summary: jsonData.treatment_history?.response_summary || ''
          },
          tumor_board_notes: {
            discussion: jsonData.tumor_board_notes?.discussion || '',
            recommendation: jsonData.tumor_board_notes?.recommendation || '',
            board_members: jsonData.tumor_board_notes?.board_members || []
          }
        }
        
        // Extract timeline entries from JSON lab_data
        const timelineEntries = []
        if (jsonData.lab_data) {
          Object.keys(jsonData.lab_data).forEach(key => {
            if (key !== 'baseline' && key !== 'derived_scores' && key !== 'follow_up') {
              timelineEntries.push({
                id: Date.now() + Math.random(), // Unique ID
                date: key,
                values: jsonData.lab_data[key] || { ALT: '', AST: '', Tbil: '', Alb: '', PT: '', INR: '' }
              })
            }
          })
          // Sort by date
          timelineEntries.sort((a, b) => new Date(a.date) - new Date(b.date))
        }
        
        setFormData(convertedData)
        setLabTimelineEntries(timelineEntries)
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
    
    // Reset file input
    if (fileInputRef.current) {
      fileInputRef.current.value = ''
    }
  }

  const handleSubmit = (e) => {
    e.preventDefault()
    const cleanedData = cleanFormData(formData)
    onSubmit(cleanedData)
  }

  return (
    <form onSubmit={handleSubmit} className="bg-white rounded-lg shadow p-6 space-y-6">
      {/* File Upload */}
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

      {/* Case ID */}
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

      {/* Demographics */}
      <div className="border-t pt-6">
        <h3 className="text-lg font-semibold mb-4">Demographics</h3>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Age</label>
            <input
              type="number"
              value={formData.demographics.age}
              onChange={(e) => handleChange('demographics.age', parseInt(e.target.value) || '')}
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
              <option value="M">Male</option>
              <option value="F">Female</option>
            </select>
          </div>
        </div>
      </div>

      {/* Clinical Summary */}
      <div className="border-t pt-6">
        <h3 className="text-lg font-semibold mb-4">Clinical Summary</h3>
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Etiology</label>
            <input
              type="text"
              value={formData.clinical_summary.etiology}
              onChange={(e) => handleChange('clinical_summary.etiology', e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-md"
              placeholder="e.g., HBV-related cirrhosis"
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
                    handleArrayAdd('clinical_summary.symptoms', symptomInput)
                    setSymptomInput('')
                  }
                }}
                className="flex-1 px-3 py-2 border border-gray-300 rounded-md"
                placeholder="Add symptom and press Enter"
              />
            </div>
            <div className="flex flex-wrap gap-2">
              {formData.clinical_summary.symptoms.map((symptom, idx) => (
                <span key={idx} className="inline-flex items-center px-3 py-1 bg-blue-100 text-blue-800 rounded-full text-sm">
                  {symptom}
                  <button
                    type="button"
                    onClick={() => handleArrayRemove('clinical_summary.symptoms', idx)}
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
                    handleArrayAdd('clinical_summary.comorbidities', comorbidityInput)
                    setComorbidityInput('')
                  }
                }}
                className="flex-1 px-3 py-2 border border-gray-300 rounded-md"
                placeholder="Add comorbidity and press Enter"
              />
            </div>
            <div className="flex flex-wrap gap-2">
              {formData.clinical_summary.comorbidities.map((comorbidity, idx) => (
                <span key={idx} className="inline-flex items-center px-3 py-1 bg-green-100 text-green-800 rounded-full text-sm">
                  {comorbidity}
                  <button
                    type="button"
                    onClick={() => handleArrayRemove('clinical_summary.comorbidities', idx)}
                    className="ml-2 text-green-600 hover:text-green-800"
                  >
                    ×
                  </button>
                </span>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Lab Data Baseline */}
      <div className="border-t pt-6">
        <h3 className="text-lg font-semibold mb-4">Lab Data - Baseline</h3>
        <div className="grid grid-cols-3 gap-4">
          {Object.keys(formData.lab_data.baseline).map((key) => (
            <div key={key}>
              <label className="block text-sm font-medium text-gray-700 mb-1">{key}</label>
              <input
                type="number"
                step="0.01"
                value={formData.lab_data.baseline[key]}
                onChange={(e) => handleChange(`lab_data.baseline.${key}`, parseFloat(e.target.value) || '')}
                className="w-full px-3 py-2 border border-gray-300 rounded-md"
              />
            </div>
          ))}
        </div>
      </div>

      {/* Lab Data Derived Scores */}
      <div className="border-t pt-6">
        <h3 className="text-lg font-semibold mb-4">Lab Data - Derived Scores</h3>
        <div className="grid grid-cols-3 gap-4">
          {Object.keys(formData.lab_data.derived_scores).map((key) => (
            <div key={key}>
              <label className="block text-sm font-medium text-gray-700 mb-1">{key}</label>
              <input
                type="text"
                value={formData.lab_data.derived_scores[key]}
                onChange={(e) => handleChange(`lab_data.derived_scores.${key}`, e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 rounded-md"
              />
            </div>
          ))}
        </div>
      </div>

      {/* Lab Data Timeline */}
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
          <p className="text-gray-500 text-sm italic">No timeline entries added yet. Click "Add Lab Results" to add follow-up lab values.</p>
        ) : (
          <div className="space-y-4">
            {[...labTimelineEntries].sort((a, b) => new Date(a.date) - new Date(b.date)).map((entry) => {
              const originalIndex = labTimelineEntries.findIndex(e => e.id === entry.id)
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
                  {Object.keys(entry.values).map((key) => (
                    <div key={key}>
                      <label className="block text-xs font-medium text-gray-600 mb-1">{key}</label>
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

      {/* Imaging */}
      <div className="border-t pt-6">
        <h3 className="text-lg font-semibold mb-4">Imaging</h3>
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Modality</label>
            <input
              type="text"
              value={formData.imaging.modality}
              onChange={(e) => handleChange('imaging.modality', e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-md"
              placeholder="e.g., CT, MRI"
            />
          </div>
        </div>
      </div>

      {/* Treatment History */}
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
                    handleArrayAdd('treatment_history.previous', previousTreatmentInput)
                    setPreviousTreatmentInput('')
                  }
                }}
                className="flex-1 px-3 py-2 border border-gray-300 rounded-md"
                placeholder="e.g., TACE, RFA"
              />
            </div>
            <div className="flex flex-wrap gap-2">
              {formData.treatment_history.previous.map((treatment, idx) => (
                <span key={idx} className="inline-flex items-center px-3 py-1 bg-yellow-100 text-yellow-800 rounded-full text-sm">
                  {treatment}
                  <button
                    type="button"
                    onClick={() => handleArrayRemove('treatment_history.previous', idx)}
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
              value={formData.treatment_history.current}
              onChange={(e) => handleChange('treatment_history.current', e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-md"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Response Summary</label>
            <textarea
              value={formData.treatment_history.response_summary}
              onChange={(e) => handleChange('treatment_history.response_summary', e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-md"
              rows="3"
            />
          </div>
        </div>
      </div>

      {/* Tumor Board Notes */}
      <div className="border-t pt-6">
        <h3 className="text-lg font-semibold mb-4">Tumor Board Notes</h3>
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Discussion</label>
            <textarea
              value={formData.tumor_board_notes.discussion}
              onChange={(e) => handleChange('tumor_board_notes.discussion', e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-md"
              rows="4"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Recommendation</label>
            <textarea
              value={formData.tumor_board_notes.recommendation}
              onChange={(e) => handleChange('tumor_board_notes.recommendation', e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-md"
              rows="3"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Board Members</label>
            <div className="flex gap-2 mb-2">
              <input
                type="text"
                value={boardMemberInput}
                onChange={(e) => setBoardMemberInput(e.target.value)}
                onKeyPress={(e) => {
                  if (e.key === 'Enter' && boardMemberInput) {
                    e.preventDefault()
                    handleArrayAdd('tumor_board_notes.board_members', boardMemberInput)
                    setBoardMemberInput('')
                  }
                }}
                className="flex-1 px-3 py-2 border border-gray-300 rounded-md"
                placeholder="e.g., Hepatologist"
              />
            </div>
            <div className="flex flex-wrap gap-2">
              {formData.tumor_board_notes.board_members.map((member, idx) => (
                <span key={idx} className="inline-flex items-center px-3 py-1 bg-purple-100 text-purple-800 rounded-full text-sm">
                  {member}
                  <button
                    type="button"
                    onClick={() => handleArrayRemove('tumor_board_notes.board_members', idx)}
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

      {/* Submit Button */}
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
