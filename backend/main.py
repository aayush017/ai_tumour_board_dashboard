from fastapi import FastAPI, HTTPException, Depends, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import List, Dict, Any
from datetime import datetime
import os

from openai import OpenAI

from database import SessionLocal, engine
from models import PatientEntity, Base
import schemas
from services.specialist_agents import (
    SpecialistAgentError,
    SpecialistModelError,
    generate_specialist_summary as run_specialist_agent,
)

# Create tables
Base.metadata.create_all(bind=engine)

def ensure_ground_truth_column():
    """Add the ground_truth column if the existing SQLite table predates this schema."""
    try:
        with engine.connect() as connection:
            columns = {
                row[1]
                for row in connection.execute(text("PRAGMA table_info(patient_entities);"))
            }
            if "ground_truth" not in columns:
                connection.execute(text("ALTER TABLE patient_entities ADD COLUMN ground_truth JSON"))
    except Exception as exc:
        print(f"[warn] Unable to verify/alter patient_entities table: {exc}")

ensure_ground_truth_column()

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

    
    from dotenv import load_dotenv

    load_dotenv()  # load .env file if present
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
        "clinical",
        "lab_data",
        "radiology",
        "pathology",
        "treatment_history",
        "tumor_board",
        "ground_truth",
    ]
    return {key: serialized.get(key) for key in allowed_keys if serialized.get(key) is not None}

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
    entries = []

    baseline = lab_data.get("baseline")
    if isinstance(baseline, dict):
        entries.append({"date": "baseline", "data": baseline})

    # Primary time-series structure
    time_series = lab_data.get("time_series")
    if isinstance(time_series, list):
        for item in time_series:
            if not isinstance(item, dict):
                continue
            date_value = item.get("date")
            data = {k: v for k, v in item.items() if k != "date" and v is not None}
            if date_value and data:
                entries.append({"date": date_value, "data": data})

    # Backwards compatibility: allow old follow_up/date keyed structures
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

    def is_date_string(value: str) -> bool:
        try:
            from datetime import datetime as _dt
            for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%Y/%m/%d", "%d/%m/%Y", "%Y-%m", "%Y/%m"):
                try:
                    _dt.strptime(value, fmt)
                    return True
                except Exception:
                    pass
            _dt.fromisoformat(value)
            return True
        except Exception:
            return False

    for k, v in lab_data.items():
        if k in ("baseline", "derived_scores", "follow_up", "time_series"):
            continue
        if is_date_string(str(k)) and isinstance(v, dict):
            entries.append({"date": k, "data": v})

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
    model_name = os.getenv("OPENAI_MODEL", "gpt-4o")

    try:
        return run_specialist_agent(
            specialist=specialist,
            patient_context=patient_context,
            client=client,
            model_name=model_name,
        )
    except SpecialistModelError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except SpecialistAgentError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
