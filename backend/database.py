"""
database.py — Database engine, session management, and initialization
Supports SQLite (dev) and PostgreSQL (prod) via DATABASE_URL env var.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

import config
from models import Base, PatientORM, PatientStatus

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

CONNECT_ARGS: dict = {}
if config.DATABASE_URL.startswith("sqlite"):
    CONNECT_ARGS = {"check_same_thread": False}

engine = create_engine(
    config.DATABASE_URL,
    connect_args=CONNECT_ARGS,
    echo=False,
    pool_pre_ping=True,       # detect stale connections
    pool_recycle=3600,
)

# Enable WAL mode for SQLite (better concurrency under multithreaded writes)
if config.DATABASE_URL.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def _set_wal(dbapi_conn, _conn_record):
        dbapi_conn.execute("PRAGMA journal_mode=WAL")
        dbapi_conn.execute("PRAGMA synchronous=NORMAL")

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# ---------------------------------------------------------------------------
# Session helpers
# ---------------------------------------------------------------------------

@contextmanager
def get_db() -> Generator[Session, None, None]:
    """Provide a transactional scope around a series of operations."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_db_session() -> Generator[Session, None, None]:
    """FastAPI dependency — yields a session and always closes it."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------

SEED_PATIENTS = [
    {"name": "Arjun Sharma",    "age": 67, "bed_number": "ICU-01", "diagnosis": "Acute MI"},
    {"name": "Priya Patel",     "age": 54, "bed_number": "ICU-02", "diagnosis": "Pneumonia"},
    {"name": "Rahul Verma",     "age": 72, "bed_number": "ICU-03", "diagnosis": "Stroke"},
    {"name": "Sunita Gupta",    "age": 45, "bed_number": "ICU-04", "diagnosis": "Sepsis"},
    {"name": "Vikram Nair",     "age": 60, "bed_number": "ICU-05", "diagnosis": "COPD Exacerbation"},
    {"name": "Meena Iyer",      "age": 38, "bed_number": "ICU-06", "diagnosis": "Pulmonary Embolism"},
    {"name": "Deepak Singh",    "age": 81, "bed_number": "ICU-07", "diagnosis": "Renal Failure"},
    {"name": "Kavitha Reddy",   "age": 29, "bed_number": "ICU-08", "diagnosis": "Trauma"},
]


def init_db() -> None:
    """Create all tables and seed patients if the DB is empty."""
    log.info("Initializing database at: %s", config.DATABASE_URL)
    Base.metadata.create_all(bind=engine)

    with get_db() as db:
        count = db.query(PatientORM).count()
        if count == 0:
            log.info("Seeding %d patients …", len(SEED_PATIENTS))
            for p in SEED_PATIENTS:
                db.add(PatientORM(**p, status=PatientStatus.STABLE))
            db.commit()
            log.info("Seed complete.")
        else:
            log.info("Database already has %d patients, skipping seed.", count)


def save_vital_record(db: Session, patient_id: int, vitals_dict: dict) -> None:
    """Persist a vital reading — called from the simulator thread."""
    from models import VitalRecordORM
    record = VitalRecordORM(patient_id=patient_id, **vitals_dict)
    db.add(record)
    # commit handled by caller context-manager


def save_alert(db: Session, alert_dict: dict) -> None:
    """Persist an alert row — called from the alert manager."""
    from models import AlertORM
    alert = AlertORM(**alert_dict)
    db.add(alert)
