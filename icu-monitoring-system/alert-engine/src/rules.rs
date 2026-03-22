// src/rules.rs – Alert rule definitions and evaluation engine

use crate::types::{Alert, AlertRule, AlertType, PatientTrend, Severity, VitalsMessage};
use chrono::Utc;
use std::collections::HashMap;
use std::sync::{Arc, Mutex};
use tracing::{info, warn};
use uuid::Uuid;

/// All clinical alert rules (following NICE/AHA guidelines)
pub fn get_alert_rules() -> Vec<AlertRule> {
    vec![
        // ── Cardiovascular ────────────────────────────────────────────────────
        AlertRule {
            name: "Tachycardia",
            alert_type: AlertType::Tachycardia,
            severity: Severity::Elevated,
            check: |v| {
                if v.heart_rate > 120.0 {
                    Some(format!(
                        "Tachycardia: HR {:.0} bpm (threshold >120)", v.heart_rate
                    ))
                } else {
                    None
                }
            },
        },
        AlertRule {
            name: "Severe Tachycardia",
            alert_type: AlertType::Tachycardia,
            severity: Severity::Critical,
            check: |v| {
                if v.heart_rate > 150.0 {
                    Some(format!(
                        "Severe tachycardia: HR {:.0} bpm – risk of haemodynamic compromise",
                        v.heart_rate
                    ))
                } else {
                    None
                }
            },
        },
        AlertRule {
            name: "Bradycardia",
            alert_type: AlertType::Bradycardia,
            severity: Severity::Critical,
            check: |v| {
                if v.heart_rate < 40.0 {
                    Some(format!(
                        "Bradycardia: HR {:.0} bpm – risk of cardiac arrest", v.heart_rate
                    ))
                } else {
                    None
                }
            },
        },
        AlertRule {
            name: "Hypertensive Crisis",
            alert_type: AlertType::HypertensiveCrisis,
            severity: Severity::Critical,
            check: |v| {
                if v.systolic_bp > 180.0 || v.diastolic_bp > 120.0 {
                    Some(format!(
                        "Hypertensive crisis: BP {:.0}/{:.0} mmHg",
                        v.systolic_bp, v.diastolic_bp
                    ))
                } else {
                    None
                }
            },
        },
        AlertRule {
            name: "Hypotensive Shock",
            alert_type: AlertType::HypotensiveShock,
            severity: Severity::Critical,
            check: |v| {
                if v.systolic_bp < 90.0 {
                    Some(format!(
                        "Hypotensive shock: SBP {:.0} mmHg – possible circulatory failure",
                        v.systolic_bp
                    ))
                } else {
                    None
                }
            },
        },

        // ── Respiratory ───────────────────────────────────────────────────────
        AlertRule {
            name: "Hypoxia",
            alert_type: AlertType::Hypoxia,
            severity: Severity::Elevated,
            check: |v| {
                if v.spo2 < 94.0 && v.spo2 >= 90.0 {
                    Some(format!("Mild hypoxia: SpO2 {:.1}% (target ≥94%)", v.spo2))
                } else {
                    None
                }
            },
        },
        AlertRule {
            name: "Severe Hypoxia",
            alert_type: AlertType::Hypoxia,
            severity: Severity::Critical,
            check: |v| {
                if v.spo2 < 90.0 {
                    Some(format!(
                        "Severe hypoxia: SpO2 {:.1}% – immediate oxygenation required",
                        v.spo2
                    ))
                } else {
                    None
                }
            },
        },
        AlertRule {
            name: "Respiratory Distress",
            alert_type: AlertType::RespiratoryDistress,
            severity: Severity::Critical,
            check: |v| {
                if v.respiratory_rate > 30.0 || v.respiratory_rate < 8.0 {
                    Some(format!(
                        "Respiratory distress: RR {:.0} breaths/min",
                        v.respiratory_rate
                    ))
                } else {
                    None
                }
            },
        },
        AlertRule {
            name: "Apnea",
            alert_type: AlertType::Apnea,
            severity: Severity::CodeBlue,
            check: |v| {
                if v.respiratory_rate < 4.0 {
                    Some(format!(
                        "Apnea: RR {:.0} – immediate airway management required",
                        v.respiratory_rate
                    ))
                } else {
                    None
                }
            },
        },

        // ── Metabolic ─────────────────────────────────────────────────────────
        AlertRule {
            name: "Hyperthermia",
            alert_type: AlertType::Hyperthermia,
            severity: Severity::Elevated,
            check: |v| {
                if v.temperature >= 38.5 {
                    Some(format!("Fever: {:.1}°C", v.temperature))
                } else {
                    None
                }
            },
        },
        AlertRule {
            name: "Severe Hyperthermia",
            alert_type: AlertType::Hyperthermia,
            severity: Severity::Critical,
            check: |v| {
                if v.temperature >= 40.0 {
                    Some(format!(
                        "Severe hyperthermia: {:.1}°C – risk of organ damage",
                        v.temperature
                    ))
                } else {
                    None
                }
            },
        },
        AlertRule {
            name: "Hypothermia",
            alert_type: AlertType::Hypothermia,
            severity: Severity::Critical,
            check: |v| {
                if v.temperature < 35.0 {
                    Some(format!(
                        "Hypothermia: {:.1}°C – active warming required",
                        v.temperature
                    ))
                } else {
                    None
                }
            },
        },
        AlertRule {
            name: "Lactic Acidosis",
            alert_type: AlertType::LacticAcidosis,
            severity: Severity::Critical,
            check: |v| {
                if v.lactate > 4.0 {
                    Some(format!(
                        "Severe lactic acidosis: {:.1} mmol/L – tissue hypoperfusion",
                        v.lactate
                    ))
                } else if v.lactate > 2.0 {
                    Some(format!("Elevated lactate: {:.1} mmol/L", v.lactate))
                } else {
                    None
                }
            },
        },
        AlertRule {
            name: "Sepsis Alert",
            alert_type: AlertType::SepsisAlert,
            severity: Severity::Critical,
            check: |v| {
                // Sepsis-3 criteria: infection + organ dysfunction
                // Proxy: SOFA-like: lactate>2 + low SBP + high HR + high RR
                let score = (if v.lactate > 2.0 { 1 } else { 0 })
                    + (if v.systolic_bp < 100.0 { 1 } else { 0 })
                    + (if v.heart_rate > 110.0 { 1 } else { 0 })
                    + (if v.respiratory_rate > 22.0 { 1 } else { 0 })
                    + (if v.temperature > 38.3 || v.temperature < 36.0 { 1 } else { 0 });

                if score >= 3 {
                    Some(format!(
                        "Possible sepsis: qSOFA-like score {} – initiate sepsis bundle",
                        score
                    ))
                } else {
                    None
                }
            },
        },
        AlertRule {
            name: "Hyperglycemia",
            alert_type: AlertType::Hyperglycemia,
            severity: Severity::Elevated,
            check: |v| {
                if v.glucose > 250.0 {
                    Some(format!("Hyperglycemia: {:.0} mg/dL", v.glucose))
                } else {
                    None
                }
            },
        },
        AlertRule {
            name: "Hypoglycemia",
            alert_type: AlertType::Hypoglycemia,
            severity: Severity::Critical,
            check: |v| {
                if v.glucose < 60.0 {
                    Some(format!(
                        "Hypoglycemia: {:.0} mg/dL – immediate glucose administration",
                        v.glucose
                    ))
                } else {
                    None
                }
            },
        },
    ]
}

/// Alert evaluation engine
pub struct RulesEngine {
    rules:  Vec<AlertRule>,
    trends: Arc<Mutex<HashMap<String, PatientTrend>>>,
}

impl RulesEngine {
    pub fn new() -> Self {
        Self {
            rules:  get_alert_rules(),
            trends: Arc::new(Mutex::new(HashMap::new())),
        }
    }

    /// Evaluate all rules against a vitals message; return triggered alerts
    pub fn evaluate(&self, vitals: &VitalsMessage) -> Vec<Alert> {
        let mut alerts = Vec::new();

        // Update trend state
        let mut trends = self.trends.lock().unwrap();
        let trend = trends
            .entry(vitals.patient_id.clone())
            .or_insert_with(|| PatientTrend {
                patient_id: vitals.patient_id.clone(),
                ..Default::default()
            });
        trend.push_vitals(vitals);
        let trend_clone = trend.clone();
        drop(trends);

        // Evaluate individual rules
        for rule in &self.rules {
            if let Some(message) = (rule.check)(vitals) {
                let alert = Alert {
                    alert_id:        Uuid::new_v4().to_string(),
                    patient_id:      vitals.patient_id.clone(),
                    alert_type:      rule.alert_type.clone(),
                    severity:        rule.severity,
                    message:         message.clone(),
                    vitals_snapshot: vitals.clone(),
                    triggered_at:    Utc::now(),
                    acknowledged:    false,
                };

                match rule.severity {
                    Severity::CodeBlue | Severity::Critical => {
                        warn!(
                            patient_id = %vitals.patient_id,
                            alert_type = %rule.alert_type,
                            severity   = %rule.severity,
                            message    = %message,
                            "🚨 ALERT"
                        );
                    }
                    _ => {
                        info!(
                            patient_id = %vitals.patient_id,
                            alert_type = %rule.alert_type,
                            message    = %message,
                            "⚠ Alert"
                        );
                    }
                }

                alerts.push(alert);
            }
        }

        // Composite trend-based: rapid deterioration
        if trend_clone.spo2_falling_fast() && trend_clone.bp_crashing() {
            let alert = Alert {
                alert_id:        Uuid::new_v4().to_string(),
                patient_id:      vitals.patient_id.clone(),
                alert_type:      AlertType::RapidDeterioration,
                severity:        Severity::CodeBlue,
                message:         "Rapid physiological deterioration: SpO2 falling + BP crashing".to_string(),
                vitals_snapshot: vitals.clone(),
                triggered_at:    Utc::now(),
                acknowledged:    false,
            };
            warn!(
                patient_id = %vitals.patient_id,
                "🆘 RAPID DETERIORATION detected by trend analysis"
            );
            alerts.push(alert);
        }

        // Code Blue on extreme severity
        if vitals.severity_level() == Severity::CodeBlue
            && !alerts.iter().any(|a| a.alert_type == AlertType::CodeBlue)
        {
            alerts.push(Alert {
                alert_id:        Uuid::new_v4().to_string(),
                patient_id:      vitals.patient_id.clone(),
                alert_type:      AlertType::CodeBlue,
                severity:        Severity::CodeBlue,
                message:         "CODE BLUE – activate emergency response team immediately".to_string(),
                vitals_snapshot: vitals.clone(),
                triggered_at:    Utc::now(),
                acknowledged:    false,
            });
        }

        alerts
    }
}
