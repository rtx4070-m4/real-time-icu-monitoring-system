// src/types.rs – Core data types for the ICU alert engine

use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use std::fmt;

/// Severity level matching the C++ core engine
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
pub enum Severity {
    Stable = 0,
    Elevated = 1,
    Critical = 2,
    CodeBlue = 3,
}

impl fmt::Display for Severity {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Severity::Stable    => write!(f, "STABLE"),
            Severity::Elevated  => write!(f, "ELEVATED"),
            Severity::Critical  => write!(f, "CRITICAL"),
            Severity::CodeBlue  => write!(f, "CODE_BLUE"),
        }
    }
}

impl From<i64> for Severity {
    fn from(v: i64) -> Self {
        match v {
            0 => Severity::Stable,
            1 => Severity::Elevated,
            2 => Severity::Critical,
            _ => Severity::CodeBlue,
        }
    }
}

/// Vital signs payload from Kafka (produced by C++ core engine)
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct VitalsMessage {
    pub patient_id:       String,
    pub heart_rate:       f64,
    pub systolic_bp:      f64,
    pub diastolic_bp:     f64,
    pub spo2:             f64,
    pub respiratory_rate: f64,
    pub temperature:      f64,
    pub glucose:          f64,
    pub lactate:          f64,
    pub severity:         i64,
    pub timestamp:        DateTime<Utc>,
}

impl VitalsMessage {
    pub fn severity_level(&self) -> Severity {
        Severity::from(self.severity)
    }
}

/// Alert categories
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
pub enum AlertType {
    // Cardiovascular
    Tachycardia,
    Bradycardia,
    HypertensiveCrisis,
    HypotensiveShock,

    // Respiratory
    Hypoxia,
    Apnea,
    RespiratoryDistress,

    // Metabolic
    Hyperthermia,
    Hypothermia,
    Hyperglycemia,
    Hypoglycemia,
    LacticAcidosis,

    // Composite
    SepsisAlert,
    CodeBlue,
    RapidDeterioration,
}

impl fmt::Display for AlertType {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        let s = serde_json::to_string(self)
            .unwrap_or_else(|_| "UNKNOWN".to_string())
            .trim_matches('"')
            .to_string();
        write!(f, "{}", s)
    }
}

/// A triggered alert record
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Alert {
    pub alert_id:     String,
    pub patient_id:   String,
    pub alert_type:   AlertType,
    pub severity:     Severity,
    pub message:      String,
    pub vitals_snapshot: VitalsMessage,
    pub triggered_at: DateTime<Utc>,
    pub acknowledged: bool,
}

/// Alert rule definition
#[derive(Debug, Clone)]
pub struct AlertRule {
    pub name:      &'static str,
    pub alert_type: AlertType,
    pub severity:   Severity,
    pub check:      fn(&VitalsMessage) -> Option<String>,
}

/// Patient trend state (for detecting rapid deterioration)
#[derive(Debug, Clone, Default)]
pub struct PatientTrend {
    pub patient_id:       String,
    pub hr_history:       Vec<f64>,
    pub spo2_history:     Vec<f64>,
    pub bp_history:       Vec<f64>,
    pub last_alert_types: Vec<AlertType>,
    pub alert_count_1min: u32,
    pub last_seen:        Option<DateTime<Utc>>,
}

impl PatientTrend {
    pub const MAX_HISTORY: usize = 10;

    pub fn push_vitals(&mut self, v: &VitalsMessage) {
        let push = |history: &mut Vec<f64>, value: f64| {
            history.push(value);
            if history.len() > Self::MAX_HISTORY {
                history.remove(0);
            }
        };

        push(&mut self.hr_history,   v.heart_rate);
        push(&mut self.spo2_history, v.spo2);
        push(&mut self.bp_history,   v.systolic_bp);
        self.last_seen = Some(v.timestamp);
    }

    /// Returns the slope (per-sample trend) of the last N readings
    pub fn slope(&self, history: &[f64]) -> f64 {
        let n = history.len();
        if n < 2 {
            return 0.0;
        }
        let last  = history[n - 1];
        let first = history[0];
        (last - first) / n as f64
    }

    pub fn spo2_falling_fast(&self) -> bool {
        self.slope(&self.spo2_history) < -0.5
    }

    pub fn bp_crashing(&self) -> bool {
        self.slope(&self.bp_history) < -1.5
    }

    pub fn hr_spiking(&self) -> bool {
        self.slope(&self.hr_history) > 2.0
    }
}
