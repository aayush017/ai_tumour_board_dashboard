from enum import Enum
from pydantic import BaseModel, Field, field_serializer
from typing import Optional, List, Dict, Any
from datetime import datetime

class Demographics(BaseModel):
    name: Optional[str] = None
    age: Optional[int] = None
    sex: Optional[str] = None

class ClinicalSummary(BaseModel):
    etiology: Optional[str] = None
    symptoms: Optional[List[str]] = None
    comorbidities: Optional[List[str]] = None

class LabData(BaseModel):
    baseline: Optional[Dict[str, Any]] = None
    follow_up: Optional[Dict[str, Any]] = None
    derived_scores: Optional[Dict[str, Any]] = None

class ImagingFindings(BaseModel):
    date: Optional[str] = None
    lesion_count: Optional[int] = None
    largest_size_cm: Optional[float] = None
    segment: Optional[int] = None
    LIRADS: Optional[int] = None
    PVTT: Optional[bool] = None
    METS: Optional[str] = None
    ECOG: Optional[int] = None

class Imaging(BaseModel):
    modality: Optional[str] = None
    findings: Optional[List[ImagingFindings]] = None
    follow_up_findings: Optional[Dict[str, str]] = None
    attachments: Optional[List[str]] = None

class Histopathology(BaseModel):
    biopsy: Optional[str] = None
    fibrosis_stage: Optional[int] = None
    comments: Optional[str] = None

class TreatmentHistory(BaseModel):
    previous: Optional[List[str]] = None
    current: Optional[str] = None
    response_summary: Optional[str] = None

class TumorBoardNotes(BaseModel):
    discussion: Optional[str] = None
    recommendation: Optional[str] = None
    board_members: Optional[List[str]] = None

class PatientCreate(BaseModel):
    case_id: str
    demographics: Optional[Demographics] = None
    clinical_summary: Optional[ClinicalSummary] = None
    # Allow arbitrary date keys inside lab_data (timeline entries)
    lab_data: Optional[Dict[str, Any]] = None
    imaging: Optional[Imaging] = None
    histopathology: Optional[Histopathology] = None
    treatment_history: Optional[TreatmentHistory] = None
    tumor_board_notes: Optional[TumorBoardNotes] = None

class PatientUpdate(BaseModel):
    demographics: Optional[Dict[str, Any]] = None
    clinical_summary: Optional[Dict[str, Any]] = None
    lab_data: Optional[Dict[str, Any]] = None
    imaging: Optional[Dict[str, Any]] = None
    histopathology: Optional[Dict[str, Any]] = None
    treatment_history: Optional[Dict[str, Any]] = None
    tumor_board_notes: Optional[Dict[str, Any]] = None

class PatientResponse(BaseModel):
    id: str
    case_id: str
    demographics: Optional[Dict[str, Any]] = None
    clinical_summary: Optional[Dict[str, Any]] = None
    lab_data: Optional[Dict[str, Any]] = None
    imaging: Optional[Dict[str, Any]] = None
    histopathology: Optional[Dict[str, Any]] = None
    treatment_history: Optional[Dict[str, Any]] = None
    tumor_board_notes: Optional[Dict[str, Any]] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
    @field_serializer('created_at', 'updated_at', when_used='always')
    def serialize_datetime(self, value: Optional[datetime], _info) -> Optional[str]:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.isoformat()
        return str(value) if value else None
    
    class Config:
        from_attributes = True

class SpecialistType(str, Enum):
    oncologist = "oncologist"
    hepatologist = "hepatologist"

class SpecialistSummaryResponse(BaseModel):
    specialist: SpecialistType
    diagnosis: str
    suggestive_plan: List[str]
    confidence: Optional[str] = None
    caveats: Optional[str] = None
    source_model: str
    generated_at: datetime
