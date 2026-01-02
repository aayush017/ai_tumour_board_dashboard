from enum import Enum
from pydantic import BaseModel, Field, field_serializer, EmailStr
from typing import Optional, List, Dict, Any
from datetime import datetime


class Sex(str, Enum):
    male = "M"
    female = "F"
    other = "Other"


class AscitesLevel(str, Enum):
    none = "none"
    mild = "mild"
    moderate = "moderate"
    severe = "severe"


class EncephalopathyGrade(str, Enum):
    none = "none"
    grade1 = "grade1"
    grade2 = "grade2"
    grade3 = "grade3"
    grade4 = "grade4"


class ECOGScore(int, Enum):
    zero = 0
    one = 1
    two = 2
    three = 3
    four = 4


class ChildPugh(str, Enum):
    A = "A"
    B = "B"
    C = "C"


class LIRADS(int, Enum):
    one = 1
    two = 2
    three = 3
    four = 4
    five = 5


class MRRECIST(str, Enum):
    CR = "CR"
    PR = "PR"
    SD = "SD"
    PD = "PD"


class Differentiation(str, Enum):
    well = "Well"
    moderate = "Moderate"
    poor = "Poor"
    undifferentiated = "Undifferentiated"


class BCLCStage(str, Enum):
    zero = "0"
    A = "A"
    B = "B"
    C = "C"
    D = "D"


class TreatmentIntent(str, Enum):
    curative = "Curative"
    palliative = "Palliative"
    downstaging = "Downstaging"
    bridge = "Bridge to transplant"


class Demographics(BaseModel):
    name: Optional[str] = None
    age: Optional[float] = None
    sex: Optional[Sex] = None
    BMI: Optional[float] = Field(default=None, alias="BMI")

    class Config:
        populate_by_name = True


class Clinical(BaseModel):
    etiology: Optional[str] = None
    symptoms: Optional[List[str]] = None
    comorbidities: Optional[List[str]] = None
    ascites: Optional[AscitesLevel] = None
    encephalopathy: Optional[EncephalopathyGrade] = None
    ECOG: Optional[ECOGScore] = None
    clinical_notes_text: Optional[str] = None


class LabBaseline(BaseModel):
    hemoglobin_g_dl: Optional[float] = None
    WBC_k: Optional[float] = None
    platelets_k: Optional[float] = None
    total_bilirubin_mg_dl: Optional[float] = None
    direct_bilirubin_mg_dl: Optional[float] = None
    AST_U_L: Optional[float] = None
    ALT_U_L: Optional[float] = None
    ALP_U_L: Optional[float] = None
    albumin_g_dl: Optional[float] = None
    INR: Optional[float] = None
    PT_sec: Optional[float] = None
    Na_mmol_L: Optional[float] = None
    creatinine_mg_dl: Optional[float] = None
    AFP_ng_ml: Optional[float] = None
    CRP_mg_L: Optional[float] = None


class LabTimeSeriesEntry(BaseModel):
    date: Optional[str] = None
    hemoglobin_g_dl: Optional[float] = None
    WBC_k: Optional[float] = None
    platelets_k: Optional[float] = None
    total_bilirubin_mg_dl: Optional[float] = None
    direct_bilirubin_mg_dl: Optional[float] = None
    AST_U_L: Optional[float] = None
    ALT_U_L: Optional[float] = None
    ALP_U_L: Optional[float] = None
    albumin_g_dl: Optional[float] = None
    INR: Optional[float] = None
    PT_sec: Optional[float] = None
    Na_mmol_L: Optional[float] = None
    creatinine_mg_dl: Optional[float] = None
    AFP_ng_ml: Optional[float] = None
    CRP_mg_L: Optional[float] = None


class LabData(BaseModel):
    baseline: Optional[LabBaseline] = None
    time_series: Optional[List[LabTimeSeriesEntry]] = None


class RadiologyFiles(BaseModel):
    radiology_pdf: Optional[str] = None
    dicom_zip: Optional[str] = None


class RadiologyStudy(BaseModel):
    date: Optional[str] = None
    modality: Optional[str] = None
    imaging_center: Optional[str] = None
    radiology_report_text: Optional[str] = None
    files: Optional[RadiologyFiles] = None


class Radiology(BaseModel):
    studies: Optional[List[RadiologyStudy]] = None


class PathologyFiles(BaseModel):
    pathology_pdf: Optional[str] = None


class Pathology(BaseModel):
    biopsy_performed: Optional[bool] = None
    pathology_report_text: Optional[str] = None
    files: Optional[PathologyFiles] = None


class TumorBoard(BaseModel):
    tb_notes_text: Optional[str] = None
    members_present: Optional[List[str]] = None


class TreatmentHistory(BaseModel):
    previous_treatments: Optional[List[str]] = None
    current_treatment: Optional[str] = None
    treatment_response_notes: Optional[str] = None


class GroundTruthClinicalScores(BaseModel):
    Child_Pugh: Optional[ChildPugh] = None
    MELD: Optional[float] = None
    MELD_Na: Optional[float] = None
    ALBI: Optional[str] = None


class GroundTruthRadiology(BaseModel):
    true_LIRADS: Optional[LIRADS] = None
    true_mRECIST: Optional[MRRECIST] = None
    true_PVTT: Optional[bool] = None


class GroundTruthPathology(BaseModel):
    true_differentiation: Optional[Differentiation] = None
    true_vascular_invasion: Optional[bool] = None


class GroundTruthTreatmentStaging(BaseModel):
    true_BCLC: Optional[BCLCStage] = None
    true_intent: Optional[TreatmentIntent] = None


class GroundTruth(BaseModel):
    clinical_scores: Optional[GroundTruthClinicalScores] = None
    radiology: Optional[GroundTruthRadiology] = None
    pathology: Optional[GroundTruthPathology] = None
    treatment_staging: Optional[GroundTruthTreatmentStaging] = None


class PatientCreate(BaseModel):
    case_id: str
    demographics: Optional[Demographics] = None
    clinical: Optional[Clinical] = None
    lab_data: Optional[LabData] = None
    radiology: Optional[Radiology] = None
    pathology: Optional[Pathology] = None
    tumor_board: Optional[TumorBoard] = None
    treatment_history: Optional[TreatmentHistory] = None
    ground_truth: Optional[GroundTruth] = None


class PatientUpdate(BaseModel):
    demographics: Optional[Dict[str, Any]] = None
    clinical: Optional[Dict[str, Any]] = None
    lab_data: Optional[Dict[str, Any]] = None
    radiology: Optional[Dict[str, Any]] = None
    pathology: Optional[Dict[str, Any]] = None
    tumor_board: Optional[Dict[str, Any]] = None
    treatment_history: Optional[Dict[str, Any]] = None
    ground_truth: Optional[Dict[str, Any]] = None


class PatientResponse(BaseModel):
    id: str
    case_id: str
    demographics: Optional[Dict[str, Any]] = None
    clinical: Optional[Dict[str, Any]] = None
    lab_data: Optional[Dict[str, Any]] = None
    radiology: Optional[Dict[str, Any]] = None
    pathology: Optional[Dict[str, Any]] = None
    tumor_board: Optional[Dict[str, Any]] = None
    treatment_history: Optional[Dict[str, Any]] = None
    ground_truth: Optional[Dict[str, Any]] = None
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


# =====================
# Auth / Admin Schemas
# =====================


class MasterLoginRequest(BaseModel):
    email: EmailStr
    password: str


class GoogleLoginRequest(BaseModel):
    id_token: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class AllowListEntryCreate(BaseModel):
    email: EmailStr

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
