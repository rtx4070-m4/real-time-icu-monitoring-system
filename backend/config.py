"""
config.py — Centralized configuration for ICU Monitoring System
All settings are environment-variable overridable for 12-factor compliance.
"""

import os
from dataclasses import dataclass, field
from typing import Dict, Tuple

# ---------------------------------------------------------------------------
# Vital thresholds  (LOW / MEDIUM / CRITICAL)  ← (min, max) per severity
# ---------------------------------------------------------------------------
VITAL_THRESHOLDS: Dict[str, Dict[str, Tuple]] = {
    "heart_rate": {
        "normal":   (60,  100),
        "low":      (50,  110),
        "medium":   (45,  120),
        "critical": (0,   999),   # anything outside medium is critical
    },
    "systolic_bp": {
        "normal":   (90,  140),
        "low":      (85,  155),
        "medium":   (75,  170),
        "critical": (0,   999),
    },
    "diastolic_bp": {
        "normal":   (60,  90),
        "low":      (55,  95),
        "medium":   (45,  105),
        "critical": (0,   999),
    },
    "spo2": {
        "normal":   (95,  100),
        "low":      (92,  100),
        "medium":   (88,  100),
        "critical": (0,   999),
    },
    "temperature": {
        "normal":   (36.1, 37.5),
        "low":      (35.5, 38.0),
        "medium":   (34.5, 39.0),
        "critical": (0,    99),
    },
    "respiratory_rate": {
        "normal":   (12,  20),
        "low":      (10,  24),
        "medium":   (8,   28),
        "critical": (0,   999),
    },
}

# ---------------------------------------------------------------------------
# Simulation
# ---------------------------------------------------------------------------
SIMULATION_INTERVAL_SEC: float = float(os.getenv("SIM_INTERVAL", "2.0"))
DEFAULT_PATIENT_COUNT: int      = int(os.getenv("PATIENT_COUNT", "8"))
MAX_HISTORY_POINTS: int         = int(os.getenv("MAX_HISTORY", "100"))

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./icu.db")

# ---------------------------------------------------------------------------
# API / Server
# ---------------------------------------------------------------------------
API_HOST: str  = os.getenv("API_HOST", "0.0.0.0")
API_PORT: int  = int(os.getenv("API_PORT", "8000"))
CORS_ORIGINS: list = os.getenv("CORS_ORIGINS", "*").split(",")

# ---------------------------------------------------------------------------
# WebSocket
# ---------------------------------------------------------------------------
WS_BROADCAST_INTERVAL: float = float(os.getenv("WS_INTERVAL", "2.0"))

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOG_LEVEL: str  = os.getenv("LOG_LEVEL", "INFO")
LOG_FORMAT: str = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"

# ---------------------------------------------------------------------------
# Scheduler
# ---------------------------------------------------------------------------
SCHEDULER_TICK_SEC: float = float(os.getenv("SCHEDULER_TICK", "1.0"))

# ---------------------------------------------------------------------------
# Alert retention
# ---------------------------------------------------------------------------
MAX_ALERT_HISTORY: int = int(os.getenv("MAX_ALERTS", "500"))
