from sqlalchemy import Column, String, Integer, Float, Boolean, JSON, DateTime, Text
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime
import uuid

Base = declarative_base()

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
