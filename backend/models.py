"""
models.py — SQLAlchemy ORM models + Pydantic schemas for ICU Monitoring System
"""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field
from sqlalchemy import (
    Column, DateTime, Enum, Float, Integer, String, Text, func,
)
from sqlalchemy.orm import DeclarativeBase


# ---------------------------------------------------------------------------
# SQLAlchemy base
# ---------------------------------------------------------------------------

class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class SeverityLevel(str, enum.Enum):
    NORMAL   = "NORMAL"
    LOW      = "LOW"
    MEDIUM   = "MEDIUM"
    CRITICAL = "CRITICAL"


class PatientStatus(str, enum.Enum):
    STABLE   = "STABLE"
    WATCH    = "WATCH"
    CRITICAL = "CRITICAL"
    OFFLINE  = "OFFLINE"


# ---------------------------------------------------------------------------
# ORM Models
# ---------------------------------------------------------------------------

class PatientORM(Base):
    __tablename__ = "patients"

    id         = Column(Integer, primary_key=True, index=True)
    name       = Column(String(100), nullable=False)
    age        = Column(Integer, nullable=False)
    bed_number = Column(String(10), nullable=False, unique=True)
    diagnosis  = Column(String(200))
    status     = Column(Enum(PatientStatus), default=PatientStatus.STABLE)
    created_at = Column(DateTime, server_default=func.now())


class VitalRecordORM(Base):
    __tablename__ = "vital_records"

    id                = Column(Integer, primary_key=True, index=True)
    patient_id        = Column(Integer, nullable=False, index=True)
    timestamp         = Column(DateTime, default=datetime.utcnow, index=True)
    heart_rate        = Column(Float)
    systolic_bp       = Column(Float)
    diastolic_bp      = Column(Float)
    spo2              = Column(Float)
    temperature       = Column(Float)
    respiratory_rate  = Column(Float)
    severity          = Column(Enum(SeverityLevel), default=SeverityLevel.NORMAL)


class AlertORM(Base):
    __tablename__ = "alerts"

    id          = Column(Integer, primary_key=True, index=True)
    patient_id  = Column(Integer, nullable=False, index=True)
    patient_name= Column(String(100))
    bed_number  = Column(String(10))
    timestamp   = Column(DateTime, default=datetime.utcnow, index=True)
    severity    = Column(Enum(SeverityLevel), nullable=False)
    vital_name  = Column(String(50))
    vital_value = Column(Float)
    message     = Column(Text)
    acknowledged= Column(Integer, default=0)   # 0=no, 1=yes  (SQLite bool)


# ---------------------------------------------------------------------------
# Pydantic Schemas  (API layer)
# ---------------------------------------------------------------------------

class VitalReading(BaseModel):
    heart_rate:       float = Field(..., description="bpm")
    systolic_bp:      float = Field(..., description="mmHg")
    diastolic_bp:     float = Field(..., description="mmHg")
    spo2:             float = Field(..., description="%")
    temperature:      float = Field(..., description="°C")
    respiratory_rate: float = Field(..., description="breaths/min")
    severity:         SeverityLevel = SeverityLevel.NORMAL
    timestamp:        datetime = Field(default_factory=datetime.utcnow)

    model_config = {"from_attributes": True}


class PatientSchema(BaseModel):
    id:         int
    name:       str
    age:        int
    bed_number: str
    diagnosis:  Optional[str] = None
    status:     PatientStatus = PatientStatus.STABLE

    model_config = {"from_attributes": True}


class AlertSchema(BaseModel):
    id:           int
    patient_id:   int
    patient_name: str
    bed_number:   str
    timestamp:    datetime
    severity:     SeverityLevel
    vital_name:   str
    vital_value:  float
    message:      str
    acknowledged: bool = False

    model_config = {"from_attributes": True}


class PatientVitalsSnapshot(BaseModel):
    """Complete real-time snapshot for WebSocket broadcasts."""
    patient:  PatientSchema
    vitals:   VitalReading
    alerts:   list[AlertSchema] = []
    priority: int = 0           # scheduler priority score (0 = normal, higher = urgent)
