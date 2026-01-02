from sqlalchemy import Column, String, Integer, Float, Boolean, JSON, DateTime, Text, ForeignKey, Enum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
import enum

Base = declarative_base()


class UserRole(str, enum.Enum):
    user = "user"
    master = "master"


class User(Base):
    """
    Application users.
    - Regular users authenticate via Google OAuth (email only, no password).
    - Master user authenticates via email/password (bcrypt hash).
    """

    __tablename__ = "users"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String, unique=True, index=True, nullable=False)
    role = Column(Enum(UserRole), nullable=False, default=UserRole.user)
    password_hash = Column(String, nullable=True)  # only used for master account

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_login_at = Column(DateTime, nullable=True)
    last_login_ip = Column(String, nullable=True)


class AllowListedEmail(Base):
    """
    Allow-list of emails permitted to log in via Google OAuth.
    """

    __tablename__ = "allow_list_emails"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String, unique=True, index=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    added_by_user_id = Column(String, ForeignKey("users.id"), nullable=True)

    added_by = relationship("User")


class AuditLog(Base):
    """
    Audit log for authentication events and protected route access.
    """

    __tablename__ = "audit_logs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)

    user_id = Column(String, ForeignKey("users.id"), nullable=True)
    user_email = Column(String, nullable=True)
    role = Column(String, nullable=True)

    ip_address = Column(String, nullable=True)
    user_agent = Column(String, nullable=True)
    route = Column(String, nullable=True)
    method = Column(String, nullable=True)
    session_id = Column(String, nullable=True)

    action = Column(String, nullable=True)  # e.g., "login", "logout", "access"
    success = Column(Boolean, default=True)
    detail = Column(Text, nullable=True)

    user = relationship("User")


class PatientEntity(Base):
    __tablename__ = "patient_entities"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    case_id = Column(String, unique=True, index=True, nullable=False)

    demographics = Column(JSON)
    clinical = Column("clinical_summary", JSON)
    lab_data = Column(JSON)
    radiology = Column("imaging", JSON)
    pathology = Column("histopathology", JSON)
    tumor_board = Column("tumor_board_notes", JSON)
    treatment_history = Column(JSON)
    ground_truth = Column(JSON)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "case_id": self.case_id,
            "demographics": self.demographics,
            "clinical": self.clinical,
            "lab_data": self.lab_data,
            "radiology": self.radiology,
            "pathology": self.pathology,
            "tumor_board": self.tumor_board,
            "treatment_history": self.treatment_history,
            "ground_truth": self.ground_truth,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
