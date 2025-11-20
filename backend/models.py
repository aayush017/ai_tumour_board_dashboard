from sqlalchemy import Column, String, Integer, Float, Boolean, JSON, DateTime, Text
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime
import uuid

Base = declarative_base()

class PatientEntity(Base):
    __tablename__ = "patient_entities"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    case_id = Column(String, unique=True, index=True, nullable=False)
    
    # Demographics
    demographics = Column(JSON)
    
    # Clinical Summary
    clinical_summary = Column(JSON)
    
    # Lab Data
    lab_data = Column(JSON)
    
    # Imaging
    imaging = Column(JSON)
    
    # Histopathology
    histopathology = Column(JSON)
    
    # Treatment History
    treatment_history = Column(JSON)
    
    # Tumor Board Notes
    tumor_board_notes = Column(JSON)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def to_dict(self):
        return {
            "id": self.id,
            "case_id": self.case_id,
            "demographics": self.demographics,
            "clinical_summary": self.clinical_summary,
            "lab_data": self.lab_data,
            "imaging": self.imaging,
            "histopathology": self.histopathology,
            "treatment_history": self.treatment_history,
            "tumor_board_notes": self.tumor_board_notes,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
