"""
ai_module/python/api_server.py
FastAPI server exposing the ICU AI prediction endpoints.
"""

import json
import logging
import os
import threading
from contextlib import asynccontextmanager
from dataclasses import asdict
from typing import Any

import kafka
import numpy as np
import uvicorn
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from predictor import ICUDeteriorationPredictor, VitalsRecord

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("icu-ai")

# ── Global predictor instance ────────────────────────────────────────────────
predictor: ICUDeteriorationPredictor = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Train model on startup, shut down Kafka consumer on exit."""
    global predictor
    logger.info("Starting ICU AI Module...")
    predictor = ICUDeteriorationPredictor()
    predictor.train_on_synthetic_data(n_patients=3000)

    # Start Kafka consumer in a background thread
    kafka_thread = threading.Thread(target=kafka_consumer_loop, daemon=True)
    kafka_thread.start()

    yield

    logger.info("ICU AI Module shutting down...")


app = FastAPI(
    title="ICU AI Module",
    description="Patient deterioration prediction and statistical analysis",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Pydantic request/response models ─────────────────────────────────────────

class VitalsRequest(BaseModel):
    patient_id:       str
    heart_rate:       float = Field(ge=10, le=300)
    systolic_bp:      float = Field(ge=40, le=300)
    diastolic_bp:     float = Field(ge=20, le=200)
    spo2:             float = Field(ge=50, le=100)
    respiratory_rate: float = Field(ge=2,  le=60)
    temperature:      float = Field(ge=30, le=44)
    glucose:          float = Field(ge=20, le=600)
    lactate:          float = Field(ge=0.1, le=20)


class PredictionResponse(BaseModel):
    patient_id:             str
    deterioration_risk:     float
    risk_category:          str
    predicted_event_hours:  float | None
    confidence:             float
    feature_importances:    dict[str, float]
    timestamp:              str


class BatchPredictionRequest(BaseModel):
    patients: list[VitalsRequest]


class HealthResponse(BaseModel):
    status:      str
    model_ready: bool
    patients_tracked: int


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/health", response_model=HealthResponse)
async def health():
    return HealthResponse(
        status           = "healthy",
        model_ready      = predictor is not None and predictor.is_trained,
        patients_tracked = len(predictor.patient_history) if predictor else 0,
    )


@app.post("/api/v1/predict", response_model=PredictionResponse)
async def predict_single(req: VitalsRequest):
    """Predict deterioration risk for a single patient."""
    if not predictor or not predictor.is_trained:
        raise HTTPException(503, "Model not ready")

    vitals = VitalsRecord(**req.model_dump())
    result = predictor.predict(vitals)
    return PredictionResponse(**asdict(result))


@app.post("/api/v1/predict/batch")
async def predict_batch(req: BatchPredictionRequest):
    """Predict deterioration risk for multiple patients simultaneously."""
    if not predictor or not predictor.is_trained:
        raise HTTPException(503, "Model not ready")

    results = []
    for patient_req in req.patients:
        vitals = VitalsRecord(**patient_req.model_dump())
        result = predictor.predict(vitals)
        results.append(asdict(result))

    return {"predictions": results, "count": len(results)}


@app.get("/api/v1/stats/{patient_id}")
async def patient_stats(patient_id: str):
    """Return statistical summary of patient vitals history."""
    if not predictor:
        raise HTTPException(503, "Model not ready")

    history = predictor.patient_history.get(patient_id, [])
    if not history:
        raise HTTPException(404, f"No history for patient {patient_id}")

    def summarise(vals: list[float]) -> dict:
        arr = np.array(vals)
        return {
            "mean":  round(float(arr.mean()), 2),
            "std":   round(float(arr.std()),  2),
            "min":   round(float(arr.min()),  2),
            "max":   round(float(arr.max()),  2),
            "trend": round(float(arr[-1] - arr[0]), 2) if len(arr) > 1 else 0.0,
        }

    return {
        "patient_id":  patient_id,
        "n_readings":  len(history),
        "heart_rate":       summarise([h.heart_rate       for h in history]),
        "systolic_bp":      summarise([h.systolic_bp      for h in history]),
        "spo2":             summarise([h.spo2             for h in history]),
        "respiratory_rate": summarise([h.respiratory_rate for h in history]),
        "temperature":      summarise([h.temperature      for h in history]),
        "lactate":          summarise([h.lactate          for h in history]),
    }


@app.get("/api/v1/risk-summary")
async def risk_summary():
    """Return aggregated risk summary across all tracked patients."""
    if not predictor or not predictor.is_trained:
        raise HTTPException(503, "Model not ready")

    results = []
    for patient_id, history in predictor.patient_history.items():
        if not history:
            continue
        latest = history[-1]
        result = predictor.predict(latest)
        results.append({
            "patient_id":         result.patient_id,
            "deterioration_risk": result.deterioration_risk,
            "risk_category":      result.risk_category,
        })

    # Sort by risk descending
    results.sort(key=lambda x: x["deterioration_risk"], reverse=True)

    counts = {cat: 0 for cat in ["IMMINENT", "HIGH", "MODERATE", "LOW"]}
    for r in results:
        counts[r["risk_category"]] += 1

    return {
        "patient_count": len(results),
        "risk_distribution": counts,
        "high_risk_patients": [r for r in results if r["deterioration_risk"] >= 0.60],
    }


# ── Kafka consumer (background thread) ────────────────────────────────────────

def kafka_consumer_loop():
    """
    Consume vitals from Kafka and run predictions automatically.
    Predictions above HIGH threshold are logged as critical events.
    """
    kafka_brokers = os.environ.get("KAFKA_BROKERS", "kafka:9092")
    topic         = os.environ.get("KAFKA_VITALS_TOPIC", "icu.vitals")

    logger.info(f"Kafka consumer thread starting: {kafka_brokers} → {topic}")

    try:
        consumer = kafka.KafkaConsumer(
            topic,
            bootstrap_servers=kafka_brokers.split(","),
            group_id="icu-ai-module",
            auto_offset_reset="latest",
            value_deserializer=lambda m: json.loads(m.decode("utf-8")),
            consumer_timeout_ms=1000,
        )
    except Exception as e:
        logger.error(f"Failed to connect to Kafka: {e}")
        return

    logger.info("Kafka consumer connected")

    for msg in consumer:
        try:
            data = msg.value
            vitals = VitalsRecord(
                patient_id       = data["patient_id"],
                heart_rate       = data["heart_rate"],
                systolic_bp      = data["systolic_bp"],
                diastolic_bp     = data["diastolic_bp"],
                spo2             = data["spo2"],
                respiratory_rate = data["respiratory_rate"],
                temperature      = data["temperature"],
                glucose          = data["glucose"],
                lactate          = data["lactate"],
            )

            if predictor and predictor.is_trained:
                result = predictor.predict(vitals)

                if result.risk_category in ("HIGH", "IMMINENT"):
                    logger.warning(
                        f"⚠ HIGH RISK: {vitals.patient_id} "
                        f"score={result.deterioration_risk:.3f} "
                        f"category={result.risk_category} "
                        f"eta={result.predicted_event_hours}h"
                    )

        except Exception as e:
            logger.error(f"Error processing Kafka message: {e}")


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run(
        "api_server:app",
        host="0.0.0.0",
        port=int(os.environ.get("AI_API_PORT", 8082)),
        reload=False,
        workers=1,
        log_level="info",
    )
