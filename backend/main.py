from fastapi import FastAPI, HTTPException, Depends, File, UploadFile, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import List, Dict, Any
from datetime import datetime
import os

from openai import OpenAI

from database import SessionLocal, engine
from models import PatientEntity, Base, User, UserRole, AllowListedEmail, AuditLog
import schemas
from services.specialist_agents import (
    SpecialistAgentError,
    SpecialistModelError,
    generate_specialist_summary as run_specialist_agent,
)
from services.agent_orchestrator import AgentOrchestrator
from auth import (
    get_db as get_auth_db,
    hash_password,
    verify_password,
    create_tokens,
    set_auth_cookies,
    clear_auth_cookies,
    decode_token,
    get_current_user,
    require_user,
    require_master,
    verify_google_id_token,
    log_audit_event,
)

# Create tables
Base.metadata.create_all(bind=engine)


def ensure_master_user():
    """
    Ensure initial master user exists with seeded credentials.
    Email: aayush22011@iiitd.ac.in
    Password: 123456 (hashed with bcrypt)
    """
    MASTER_EMAIL = "aayush22011@iiitd.ac.in"
    MASTER_PASSWORD = "123456"

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == MASTER_EMAIL).first()
        if not user:
            pw_hash = hash_password(MASTER_PASSWORD)
            master = User(
                email=MASTER_EMAIL,
                role=UserRole.master,
                password_hash=pw_hash,
            )
            db.add(master)
            db.commit()
    finally:
        db.close()


ensure_master_user()

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

# Dependency for database session (for legacy usage)
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


# ==========================
# AUTHENTICATION ENDPOINTS
# ==========================


@app.post("/auth/login/master")
def login_master(
    request: Request,
    form: schemas.MasterLoginRequest,
    db: Session = Depends(get_auth_db),
):
    """
    Email/password login for master user only.
    """
    user = db.query(User).filter(User.email == form.email).first()
    if not user or user.role != UserRole.master or not verify_password(
        form.password, user.password_hash or ""
    ):
        # Log failed attempt
        log_audit_event(
            db,
            action="login_master",
            request=request,
            user=None,
            role="master",
            session_id=None,
            success=False,
            detail=f"Failed master login for {form.email}",
        )
        raise HTTPException(status_code=401, detail="Invalid credentials")

    access_token, refresh_token, session_id = create_tokens(user=user)
    user.last_login_at = datetime.utcnow()
    user.last_login_ip = request.client.host if request.client else None
    db.commit()

    response = {"message": "Master login successful", "role": user.role.value, "email": user.email}

    # Create real Response to attach cookies in FastAPI automatically
    from fastapi.responses import JSONResponse

    res = JSONResponse(content=response)
    set_auth_cookies(res, access_token, refresh_token)

    log_audit_event(
        db,
        action="login_master",
        request=request,
        user=user,
        role=user.role.value,
        session_id=session_id,
        success=True,
    )
    return res


@app.post("/auth/login/google")
def login_google(
    request: Request,
    payload: schemas.GoogleLoginRequest,
    db: Session = Depends(get_auth_db),
):
    """
    Google OAuth-based login.
    Expects an ID token from the frontend, verifies it, and checks allow-list.
    """
    email = verify_google_id_token(payload.id_token)

    # Check allow-list
    allowed = db.query(AllowListedEmail).filter(AllowListedEmail.email == email).first()
    if not allowed:
        log_audit_event(
            db,
            action="login_google",
            request=request,
            user=None,
            role="user",
            session_id=None,
            success=False,
            detail=f"Google login attempted for non-allow-listed email {email}",
        )
        raise HTTPException(
            status_code=403,
            detail="This email is not authorized to access the dashboard.",
        )

    # Ensure user exists
    user = db.query(User).filter(User.email == email).first()
    if not user:
        user = User(email=email, role=UserRole.user, password_hash=None)
        db.add(user)
        db.commit()
        db.refresh(user)

    access_token, refresh_token, session_id = create_tokens(user=user)
    user.last_login_at = datetime.utcnow()
    user.last_login_ip = request.client.host if request.client else None
    db.commit()

    from fastapi.responses import JSONResponse

    res = JSONResponse(
        content={"message": "Login successful", "role": user.role.value, "email": user.email}
    )
    set_auth_cookies(res, access_token, refresh_token)

    log_audit_event(
        db,
        action="login_google",
        request=request,
        user=user,
        role=user.role.value,
        session_id=session_id,
        success=True,
    )
    return res


@app.post("/auth/refresh")
def refresh_token(request: Request, db: Session = Depends(get_auth_db)):
    """
    Refresh access token using refresh_token cookie.
    """
    token = request.cookies.get("refresh_token")
    if not token:
        raise HTTPException(status_code=401, detail="No refresh token")

    payload = decode_token(token, expected_type="refresh")
    user_id = payload.get("sub")
    role = payload.get("role")
    session_id = payload.get("sid")

    user = db.query(User).filter(User.id == user_id).first()
    if not user or user.role.value != role:
        raise HTTPException(status_code=401, detail="Invalid user")

    access_token, refresh_token, new_session_id = create_tokens(user=user, session_id=session_id)

    from fastapi.responses import JSONResponse

    res = JSONResponse(
        content={"message": "Token refreshed", "role": user.role.value, "email": user.email}
    )
    set_auth_cookies(res, access_token, refresh_token)

    log_audit_event(
        db,
        action="refresh",
        request=request,
        user=user,
        role=user.role.value,
        session_id=new_session_id,
        success=True,
    )
    return res


@app.post("/auth/logout")
def logout(
    request: Request,
    db: Session = Depends(get_auth_db),
    user_ctx=Depends(get_current_user),
):
    user, role, session_id = user_ctx

    from fastapi.responses import JSONResponse

    res = JSONResponse(content={"message": "Logged out"})
    clear_auth_cookies(res)

    log_audit_event(
        db,
        action="logout",
        request=request,
        user=user,
        role=role,
        session_id=session_id,
        success=True,
    )
    return res


@app.get("/auth/me")
def auth_me(user_ctx=Depends(get_current_user)):
    user, role, session_id = user_ctx
    return {"email": user.email, "role": role, "session_id": session_id}


# ==========================
# MASTER ADMIN ENDPOINTS
# ==========================


@app.post("/admin/change-password")
def change_master_password(
    request: Request,
    payload: schemas.ChangePasswordRequest,
    db: Session = Depends(get_auth_db),
    master_ctx=Depends(require_master),
):
    user, role, session_id = master_ctx

    if not verify_password(payload.current_password, user.password_hash or ""):
        raise HTTPException(status_code=400, detail="Current password is incorrect")

    user.password_hash = hash_password(payload.new_password)
    db.commit()

    log_audit_event(
        db,
        action="change_password",
        request=request,
        user=user,
        role=role,
        session_id=session_id,
        success=True,
    )
    return {"message": "Password updated successfully"}


@app.get("/admin/allow-list")
def list_allow_list(
    db: Session = Depends(get_auth_db),
    master_ctx=Depends(require_master),
):
    entries = db.query(AllowListedEmail).order_by(AllowListedEmail.created_at.desc()).all()
    return [
        {"id": e.id, "email": e.email, "created_at": e.created_at.isoformat()}
        for e in entries
    ]


@app.post("/admin/allow-list")
def add_allow_list_entry(
    payload: schemas.AllowListEntryCreate,
    db: Session = Depends(get_auth_db),
    master_ctx=Depends(require_master),
):
    user, role, session_id = master_ctx

    existing = db.query(AllowListedEmail).filter(AllowListedEmail.email == payload.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already in allow-list")

    entry = AllowListedEmail(email=payload.email, added_by_user_id=user.id)
    db.add(entry)
    db.commit()

    return {"id": entry.id, "email": entry.email, "created_at": entry.created_at.isoformat()}


@app.delete("/admin/allow-list/{entry_id}")
def remove_allow_list_entry(
    entry_id: str,
    db: Session = Depends(get_auth_db),
    master_ctx=Depends(require_master),
):
    entry = db.query(AllowListedEmail).filter(AllowListedEmail.id == entry_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
    db.delete(entry)
    db.commit()
    return {"message": "Entry removed"}


@app.get("/admin/audit-logs")
def get_audit_logs(
    limit: int = 100,
    db: Session = Depends(get_auth_db),
    master_ctx=Depends(require_master),
):
    limit = max(1, min(limit, 500))
    logs = (
        db.query(AuditLog)
        .order_by(AuditLog.timestamp.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": log.id,
            "timestamp": log.timestamp.isoformat() if log.timestamp else None,
            "user_email": log.user_email,
            "role": log.role,
            "ip_address": log.ip_address,
            "route": log.route,
            "method": log.method,
            "session_id": log.session_id,
            "action": log.action,
            "success": log.success,
            "detail": log.detail,
        }
        for log in logs
    ]

@app.get("/api/patients", response_model=List[schemas.PatientResponse])
def get_all_patients(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    user_ctx=Depends(require_user),
):
    """Get all patient entities"""
    patients = db.query(PatientEntity).offset(skip).limit(limit).all()
    return patients

@app.get("/api/patients/{case_id}", response_model=schemas.PatientResponse)
def get_patient(
    case_id: str,
    db: Session = Depends(get_db),
    user_ctx=Depends(require_user),
):
    """Get a specific patient by case_id"""
    patient = db.query(PatientEntity).filter(PatientEntity.case_id == case_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    return patient

@app.post("/api/patients", response_model=schemas.PatientResponse)
def create_patient(
    patient: schemas.PatientCreate,
    db: Session = Depends(get_db),
    user_ctx=Depends(require_user),
):
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
def update_patient(
    case_id: str,
    patient_update: schemas.PatientUpdate,
    db: Session = Depends(get_db),
    user_ctx=Depends(require_user),
):
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
def delete_patient(
    case_id: str,
    db: Session = Depends(get_db),
    user_ctx=Depends(require_user),
):
    """Delete a patient entity"""
    db_patient = db.query(PatientEntity).filter(PatientEntity.case_id == case_id).first()
    if not db_patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    
    db.delete(db_patient)
    db.commit()
    return {"message": "Patient deleted successfully"}

@app.get("/api/patients/{case_id}/lab-timeline")
def get_lab_timeline(
    case_id: str,
    db: Session = Depends(get_db),
    user_ctx=Depends(require_user),
):
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

@app.post("/api/patients/{case_id}/agent-summary")
def generate_agent_summary(
    case_id: str,
    db: Session = Depends(get_db),
    user_ctx=Depends(require_user),
):
    """
    Generate comprehensive agent summary using sequential processing:
    1. Processes three agents (Radiology, Clinical, Pathology)
    2. Formats output in structured format (similar to sampleOUTPUTpatient.json)
    3. Feeds to HCC Tumor Board System (if configured via INASL_PDF_PATH)
    4. Processes Tumor Board Summary Agent
    5. Returns all outputs including individual agent responses, tumor board analysis, and summary
    
    Optional: Configure INASL_PDF_PATH environment variable to enable HCC tumor board system analysis.
    """
    patient = db.query(PatientEntity).filter(PatientEntity.case_id == case_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    patient_context = build_patient_context(patient)
    if not patient_context:
        raise HTTPException(
            status_code=400,
            detail="Patient data is insufficient to generate agent summaries.",
        )

    try:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise HTTPException(
                status_code=500,
                detail="OPENAI_API_KEY is not configured on the server."
            )
        
        # Optional: Pass PDF path for tumor board system if configured
        tumor_board_pdf_path = os.getenv("INASL_PDF_PATH")
        orchestrator = AgentOrchestrator(
            openai_api_key=api_key,
            tumor_board_pdf_path=tumor_board_pdf_path
        )
        result = orchestrator.process_all(patient_context)
        return result
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error generating agent summaries: {str(exc)}") from exc

@app.post(
    "/api/patients/{case_id}/specialists/{specialist}/summary",
    response_model=schemas.SpecialistSummaryResponse,
)
def generate_specialist_summary(
    case_id: str,
    specialist: schemas.SpecialistType,
    db: Session = Depends(get_db),
    user_ctx=Depends(require_user),
):
    """
    [DEPRECATED] Generate an AI-assisted diagnosis and plan for a given specialist.
    Use /api/patients/{case_id}/agent-summary instead for comprehensive analysis.
    """
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
