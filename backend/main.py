from fastapi import FastAPI, HTTPException, Depends, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from datetime import datetime
import os
import json

from openai import OpenAI, OpenAIError

from database import SessionLocal, engine
from models import PatientEntity, Base
import schemas

# Create tables
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Patient Entity Management System", version="1.0.0")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Dependency for database session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

_openai_client = None

def get_openai_client() -> OpenAI:
    global _openai_client
    if _openai_client:
        return _openai_client

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=500,
            detail="OPENAI_API_KEY is not configured on the server. Set it before requesting AI summaries."
        )
    _openai_client = OpenAI(api_key=api_key)
    return _openai_client

def build_patient_context(patient: PatientEntity) -> Dict[str, Any]:
    serialized = schemas.PatientResponse.model_validate(patient).model_dump()
    allowed_keys = [
        "case_id",
        "demographics",
        "clinical_summary",
        "lab_data",
        "imaging",
        "histopathology",
        "treatment_history",
        "tumor_board_notes",
    ]
    return {key: serialized.get(key) for key in allowed_keys if serialized.get(key) is not None}

def parse_ai_response(raw_text: str) -> Dict[str, Any]:
    try:
        return json.loads(raw_text)
    except json.JSONDecodeError:
        return {"diagnosis": raw_text.strip(), "plan_of_action": []}

def normalize_plan(plan_data) -> List[str]:
    if isinstance(plan_data, list):
        return [str(item).strip() for item in plan_data if str(item).strip()]
    if isinstance(plan_data, str):
        return [plan_data.strip()] if plan_data.strip() else []
    return []

@app.get("/")
def read_root():
    return {"message": "Patient Entity Management API"}

@app.get("/api/patients", response_model=List[schemas.PatientResponse])
def get_all_patients(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    """Get all patient entities"""
    patients = db.query(PatientEntity).offset(skip).limit(limit).all()
    return patients

@app.get("/api/patients/{case_id}", response_model=schemas.PatientResponse)
def get_patient(case_id: str, db: Session = Depends(get_db)):
    """Get a specific patient by case_id"""
    patient = db.query(PatientEntity).filter(PatientEntity.case_id == case_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    return patient

@app.post("/api/patients", response_model=schemas.PatientResponse)
def create_patient(patient: schemas.PatientCreate, db: Session = Depends(get_db)):
    """Create a new patient entity"""
    # Check if case_id already exists
    existing = db.query(PatientEntity).filter(PatientEntity.case_id == patient.case_id).first()
    if existing:
        raise HTTPException(status_code=400, detail="Case ID already exists")
    
    db_patient = PatientEntity(**patient.model_dump())
    db.add(db_patient)
    db.commit()
    db.refresh(db_patient)
    return db_patient

@app.put("/api/patients/{case_id}", response_model=schemas.PatientResponse)
def update_patient(case_id: str, patient_update: schemas.PatientUpdate, db: Session = Depends(get_db)):
    """Update an existing patient entity"""
    db_patient = db.query(PatientEntity).filter(PatientEntity.case_id == case_id).first()
    if not db_patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    
    # Update only provided fields
    update_data = patient_update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_patient, key, value)
    
    db.commit()
    db.refresh(db_patient)
    return db_patient

@app.delete("/api/patients/{case_id}")
def delete_patient(case_id: str, db: Session = Depends(get_db)):
    """Delete a patient entity"""
    db_patient = db.query(PatientEntity).filter(PatientEntity.case_id == case_id).first()
    if not db_patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    
    db.delete(db_patient)
    db.commit()
    return {"message": "Patient deleted successfully"}

@app.get("/api/patients/{case_id}/lab-timeline")
def get_lab_timeline(case_id: str, db: Session = Depends(get_db)):
    """Get lab data timeline for a patient"""
    patient = db.query(PatientEntity).filter(PatientEntity.case_id == case_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    
    if not patient.lab_data:
        return {"timeline": []}
    
    lab_data = patient.lab_data

    def is_date_string(value: str) -> bool:
        try:
            # Try multiple common formats; fall back to False on failure
            from datetime import datetime as _dt
            for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%Y/%m/%d", "%d/%m/%Y", "%Y-%m", "%Y/%m"):
                try:
                    _dt.strptime(value, fmt)
                    return True
                except Exception:
                    pass
            # ISO-like
            _dt.fromisoformat(value)  # may raise
            return True
        except Exception:
            return False

    entries = []

    # Baseline first if present
    baseline = lab_data.get("baseline")
    if isinstance(baseline, dict):
        entries.append({"date": "baseline", "data": baseline})

    # Flatten follow_up structures if present
    follow_up = lab_data.get("follow_up")
    if isinstance(follow_up, dict):
        for k, v in follow_up.items():
            if isinstance(v, dict):
                entries.append({"date": k, "data": v})
    elif isinstance(follow_up, list):
        for item in follow_up:
            if isinstance(item, dict):
                d = item.get("date")
                data = item.get("data") or {kk: vv for kk, vv in item.items() if kk != "date"}
                if d and isinstance(data, dict):
                    entries.append({"date": d, "data": data})

    # Include any other top-level date-like keys
    for k, v in lab_data.items():
        if k in ("baseline", "derived_scores", "follow_up"):
            continue
        if is_date_string(str(k)) and isinstance(v, dict):
            entries.append({"date": k, "data": v})

    # Deduplicate by date, preserving the first occurrence (baseline label kept as 'baseline')
    seen = set()
    deduped = []
    for e in entries:
        key = e["date"]
        if key in seen:
            continue
        seen.add(key)
        deduped.append(e)

    # Sort chronologically with baseline first, then by parsed date
    from datetime import datetime as _dt
    def sort_key(e):
        if e["date"] == "baseline":
            return (_dt.min, 0)
        d = e["date"]
        # Try ISO first; fallbacks above
        try:
            return (_dt.fromisoformat(d), 1)
        except Exception:
            # Try a few common formats
            for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%Y/%m/%d", "%d/%m/%Y", "%Y-%m", "%Y/%m"):
                try:
                    return (_dt.strptime(d, fmt), 1)
                except Exception:
                    continue
        # Unsortable strings go to the end in original order
        return (_dt.max, 1)

    deduped.sort(key=sort_key)

    return {"timeline": deduped}

@app.post(
    "/api/patients/{case_id}/specialists/{specialist}/summary",
    response_model=schemas.SpecialistSummaryResponse,
)
def generate_specialist_summary(
    case_id: str,
    specialist: schemas.SpecialistType,
    db: Session = Depends(get_db),
):
    """Generate an AI-assisted diagnosis and plan for a given specialist."""
    patient = db.query(PatientEntity).filter(PatientEntity.case_id == case_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    patient_context = build_patient_context(patient)
    if not patient_context:
        raise HTTPException(
            status_code=400,
            detail="Patient data is insufficient to generate a specialist summary.",
        )

    client = get_openai_client()
    model_name = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    system_prompt = (
        f"You are a board-certified {specialist.value} contributing to a liver tumor board. "
        "Offer a cautious, evidence-based assessment."
    )
    user_prompt = (
        "You are reviewing the following patient data. "
        "Produce JSON with keys: diagnosis (string), suggestive_plan (array of strings), "
        "confidence (string, optional), caveats (string, optional). "
        "Keep recommendations actionable but concise.\n\n"
        f"Patient data:\n{json.dumps(patient_context, indent=2)}"
    )

    try:
        response = client.chat.completions.create(
            model=model_name,
            temperature=0.2,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
    except OpenAIError as exc:
        raise HTTPException(status_code=502, detail=f"OpenAI API error: {exc}") from exc

    content = ""
    if response.choices:
        content = response.choices[0].message.content or ""

    parsed = parse_ai_response(content)

    plan_data = (
        parsed.get("suggestive_plan")
        or parsed.get("plan_of_action")
        or parsed.get("plan")
        or parsed.get("recommendations")
    )
    plan = normalize_plan(plan_data)
    if not plan:
        plan = ["Review with multidisciplinary tumor board for individualized planning."]

    diagnosis = parsed.get("diagnosis") or parsed.get("assessment") or "No diagnosis generated."
    confidence = parsed.get("confidence") or parsed.get("confidence_level")
    caveats = parsed.get("caveats") or parsed.get("risks") or parsed.get("considerations")

    return schemas.SpecialistSummaryResponse(
        specialist=specialist,
        diagnosis=diagnosis.strip(),
        suggestive_plan=plan,
        confidence=confidence.strip() if isinstance(confidence, str) else confidence,
        caveats=caveats.strip() if isinstance(caveats, str) else caveats,
        source_model=model_name,
        generated_at=datetime.utcnow(),
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
