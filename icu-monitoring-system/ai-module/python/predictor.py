"""
ai_module/python/predictor.py
ICU Patient Deterioration Predictor
Uses an ensemble of ML models to predict patient deterioration risk score (0–1)
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional

import numpy as np
import pandas as pd
from sklearn.ensemble import (
    GradientBoostingClassifier,
    RandomForestClassifier,
    VotingClassifier,
)
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.model_selection import cross_val_score

logger = logging.getLogger(__name__)


@dataclass
class VitalsRecord:
    """Single vitals observation for one patient."""
    patient_id:       str
    heart_rate:       float
    systolic_bp:      float
    diastolic_bp:     float
    spo2:             float
    respiratory_rate: float
    temperature:      float
    glucose:          float
    lactate:          float
    timestamp:        str = field(default_factory=lambda: datetime.utcnow().isoformat())


@dataclass
class PredictionResult:
    patient_id:             str
    deterioration_risk:     float   # 0.0 – 1.0
    risk_category:          str     # LOW | MODERATE | HIGH | IMMINENT
    predicted_event_hours:  Optional[float]   # estimated hours until critical event
    confidence:             float
    feature_importances:    dict
    timestamp:              str = field(default_factory=lambda: datetime.utcnow().isoformat())


class ICUDeteriorationPredictor:
    """
    Ensemble ML model for ICU patient deterioration prediction.
    
    Models combined:
      - GradientBoostingClassifier (primary)
      - RandomForestClassifier (secondary)
      - LogisticRegression (linear baseline)
    
    Features engineered from vitals history:
      - Current values (8 vitals)
      - Rate-of-change for last 5 observations
      - Rolling statistics (mean, std, min, max)
      - NEWS2 score components
      - Interaction terms (SpO2 × HR, Lactate × BP)
    """

    # Clinical feature names
    FEATURES = [
        "heart_rate", "systolic_bp", "diastolic_bp",
        "spo2", "respiratory_rate", "temperature",
        "glucose", "lactate",
        # Derived features
        "pulse_pressure", "map",          # MAP = diastolic + 1/3 pulse pressure
        "shock_index",                    # HR / SBP (>1.0 = shock)
        "spo2_hr_product",               # SpO2 × HR interaction
        "lactate_bp_ratio",              # Lactate / SBP
        "news2_score",                   # NEWS2 composite score
        # Rolling statistics (last 5 readings)
        "hr_mean", "hr_std", "hr_delta",
        "spo2_mean", "spo2_std", "spo2_delta",
        "bp_mean", "bp_std", "bp_delta",
        "rr_mean", "rr_std",
        "temp_delta",
        "lactate_delta",
    ]

    def __init__(self):
        self.model: Optional[Pipeline] = None
        self.patient_history: dict[str, list[VitalsRecord]] = {}
        self.is_trained = False
        self._build_model()

    def _build_model(self):
        """Construct the ensemble voting classifier pipeline."""
        gb_clf = GradientBoostingClassifier(
            n_estimators=200,
            max_depth=4,
            learning_rate=0.05,
            subsample=0.8,
            min_samples_leaf=5,
            random_state=42,
        )
        rf_clf = RandomForestClassifier(
            n_estimators=150,
            max_depth=6,
            min_samples_leaf=4,
            n_jobs=-1,
            random_state=42,
        )
        lr_clf = LogisticRegression(
            C=0.1,
            solver="lbfgs",
            max_iter=500,
            random_state=42,
        )

        ensemble = VotingClassifier(
            estimators=[
                ("gb", gb_clf),
                ("rf", rf_clf),
                ("lr", lr_clf),
            ],
            voting="soft",
            weights=[3, 2, 1],   # GBM weighted highest
        )

        self.model = Pipeline([
            ("scaler", StandardScaler()),
            ("clf",    ensemble),
        ])

        logger.info("ICU deterioration predictor model built (GBM + RF + LR ensemble)")

    def train_on_synthetic_data(self, n_patients: int = 2000):
        """
        Train on synthetically generated ICU patient data.
        In production, replace with real EHR training data.
        """
        logger.info(f"Generating synthetic training data for {n_patients} patients...")

        rng = np.random.default_rng(42)
        records = []
        labels  = []

        for i in range(n_patients):
            # 30% deterioration cases, 70% stable
            is_deteriorating = rng.random() < 0.30

            if is_deteriorating:
                # Sick patient baseline
                hr   = rng.normal(110, 20)
                sbp  = rng.normal(95, 20)
                dbp  = rng.normal(60, 15)
                spo2 = rng.normal(91, 4)
                rr   = rng.normal(26, 6)
                temp = rng.normal(38.8, 0.8)
                gluc = rng.normal(180, 60)
                lact = rng.normal(3.5, 1.5)
            else:
                # Stable patient baseline
                hr   = rng.normal(80, 12)
                sbp  = rng.normal(125, 18)
                dbp  = rng.normal(78, 12)
                spo2 = rng.normal(97, 1.5)
                rr   = rng.normal(16, 3)
                temp = rng.normal(37.0, 0.4)
                gluc = rng.normal(100, 25)
                lact = rng.normal(1.0, 0.4)

            v = VitalsRecord(
                patient_id       = f"TRAIN_{i:04d}",
                heart_rate       = float(np.clip(hr,   30, 200)),
                systolic_bp      = float(np.clip(sbp,  50, 250)),
                diastolic_bp     = float(np.clip(dbp,  30, 150)),
                spo2             = float(np.clip(spo2, 70, 100)),
                respiratory_rate = float(np.clip(rr,    4,  50)),
                temperature      = float(np.clip(temp, 34, 42)),
                glucose          = float(np.clip(gluc, 40, 500)),
                lactate          = float(np.clip(lact, 0.3, 15)),
            )
            records.append(v)
            labels.append(int(is_deteriorating))

        # Build feature matrix
        X = np.array([self._extract_features(r, []) for r in records])
        y = np.array(labels)

        logger.info(f"Training on {len(X)} samples, {y.sum()} deterioration events...")

        # Cross-validation for performance estimate
        cv_scores = cross_val_score(self.model, X, y, cv=5, scoring="roc_auc")
        logger.info(f"CV AUC-ROC: {cv_scores.mean():.3f} ± {cv_scores.std():.3f}")

        self.model.fit(X, y)
        self.is_trained = True
        logger.info("Model trained successfully")

    def predict(self, vitals: VitalsRecord) -> PredictionResult:
        """Predict deterioration risk for a single patient observation."""
        if not self.is_trained:
            logger.warning("Model not trained – training on synthetic data first")
            self.train_on_synthetic_data()

        # Update patient history (keep last 10 readings)
        history = self.patient_history.setdefault(vitals.patient_id, [])
        history.append(vitals)
        if len(history) > 10:
            history.pop(0)

        # Extract features
        feature_vector = self._extract_features(vitals, history[:-1])
        X = np.array([feature_vector])

        # Predict
        proba = self.model.predict_proba(X)[0]
        risk_score = float(proba[1])  # probability of deterioration

        # Risk category
        if risk_score >= 0.80:
            risk_category = "IMMINENT"
        elif risk_score >= 0.60:
            risk_category = "HIGH"
        elif risk_score >= 0.35:
            risk_category = "MODERATE"
        else:
            risk_category = "LOW"

        # Estimate hours to critical event (heuristic based on risk gradient)
        if risk_score > 0.80:
            predicted_hours = 0.5
        elif risk_score > 0.60:
            predicted_hours = 2.0
        elif risk_score > 0.35:
            predicted_hours = 6.0
        else:
            predicted_hours = None

        # Feature importance (from GBM sub-model)
        try:
            gb_model = self.model.named_steps["clf"].estimators_[0][1]
            importances = dict(zip(self.FEATURES, gb_model.feature_importances_))
            top_features = dict(sorted(importances.items(),
                                       key=lambda x: x[1], reverse=True)[:5])
        except Exception:
            top_features = {}

        return PredictionResult(
            patient_id            = vitals.patient_id,
            deterioration_risk    = round(risk_score, 4),
            risk_category         = risk_category,
            predicted_event_hours = predicted_hours,
            confidence            = round(float(np.max(proba)), 4),
            feature_importances   = top_features,
        )

    def _extract_features(
        self,
        v: VitalsRecord,
        history: list[VitalsRecord],
    ) -> list[float]:
        """Compute the full feature vector for a vitals observation."""

        # ── Primary vitals ────────────────────────────────────────────────────
        hr   = v.heart_rate
        sbp  = v.systolic_bp
        dbp  = v.diastolic_bp
        spo2 = v.spo2
        rr   = v.respiratory_rate
        temp = v.temperature
        gluc = v.glucose
        lact = v.lactate

        # ── Derived physiological features ────────────────────────────────────
        pulse_pressure   = sbp - dbp
        map_val          = dbp + pulse_pressure / 3.0
        shock_index      = hr / max(sbp, 1.0)
        spo2_hr_product  = spo2 * hr / 100.0
        lactate_bp_ratio = lact / max(sbp, 1.0)

        # NEWS2 score
        news2 = self._compute_news2(v)

        # ── Rolling statistics ────────────────────────────────────────────────
        def rolling_stats(history_vals: list[float], current: float):
            if not history_vals:
                return current, 0.0, 0.0  # mean, std, delta
            arr   = np.array(history_vals + [current])
            mean  = float(np.mean(arr))
            std   = float(np.std(arr))
            delta = current - history_vals[-1] if history_vals else 0.0
            return mean, std, delta

        hr_hist   = [h.heart_rate       for h in history]
        spo2_hist = [h.spo2             for h in history]
        bp_hist   = [h.systolic_bp      for h in history]
        rr_hist   = [h.respiratory_rate for h in history]
        temp_hist = [h.temperature      for h in history]
        lact_hist = [h.lactate          for h in history]

        hr_mean,   hr_std,   hr_delta   = rolling_stats(hr_hist,   hr)
        spo2_mean, spo2_std, spo2_delta = rolling_stats(spo2_hist, spo2)
        bp_mean,   bp_std,   bp_delta   = rolling_stats(bp_hist,   sbp)
        rr_mean,   rr_std,   _          = rolling_stats(rr_hist,   rr)
        _,         _,        temp_delta = rolling_stats(temp_hist, temp)
        _,         _,        lact_delta = rolling_stats(lact_hist, lact)

        return [
            hr, sbp, dbp, spo2, rr, temp, gluc, lact,
            pulse_pressure, map_val, shock_index,
            spo2_hr_product, lactate_bp_ratio, news2,
            hr_mean, hr_std, hr_delta,
            spo2_mean, spo2_std, spo2_delta,
            bp_mean, bp_std, bp_delta,
            rr_mean, rr_std,
            temp_delta,
            lact_delta,
        ]

    @staticmethod
    def _compute_news2(v: VitalsRecord) -> float:
        """Compute NEWS2 composite early-warning score."""
        score = 0

        if v.respiratory_rate <= 8:                         score += 3
        elif v.respiratory_rate <= 11:                      score += 1
        elif v.respiratory_rate <= 20:                      score += 0
        elif v.respiratory_rate <= 24:                      score += 2
        else:                                               score += 3

        if v.spo2 <= 91:                                    score += 3
        elif v.spo2 <= 93:                                  score += 2
        elif v.spo2 <= 95:                                  score += 1

        if v.systolic_bp <= 90:                             score += 3
        elif v.systolic_bp <= 100:                          score += 2
        elif v.systolic_bp <= 110:                          score += 1
        elif v.systolic_bp > 219:                           score += 3

        if v.heart_rate <= 40:                              score += 3
        elif v.heart_rate <= 50:                            score += 1
        elif v.heart_rate <= 90:                            score += 0
        elif v.heart_rate <= 110:                           score += 1
        elif v.heart_rate <= 130:                           score += 2
        else:                                               score += 3

        if v.temperature <= 35.0:                           score += 3
        elif v.temperature <= 36.0:                         score += 1
        elif v.temperature <= 38.0:                         score += 0
        elif v.temperature <= 39.0:                         score += 1
        else:                                               score += 2

        if v.lactate > 4.0:                                 score += 3
        elif v.lactate > 2.0:                               score += 1

        return float(score)
