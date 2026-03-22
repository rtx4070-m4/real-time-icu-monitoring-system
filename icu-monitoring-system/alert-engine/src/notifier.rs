// src/notifier.rs – Sends alerts to the backend API and optionally re-publishes to Kafka

use crate::types::Alert;
use reqwest::Client;
use serde_json::json;
use tracing::{error, info, warn};

pub struct AlertNotifier {
    http:        Client,
    backend_url: String,
    kafka_topic: String,
}

impl AlertNotifier {
    pub fn new(backend_url: &str, kafka_topic: &str) -> Self {
        let http = Client::builder()
            .timeout(std::time::Duration::from_secs(5))
            .build()
            .expect("Failed to build HTTP client");

        Self {
            http,
            backend_url: backend_url.to_string(),
            kafka_topic: kafka_topic.to_string(),
        }
    }

    /// POST the alert to the backend REST API
    pub async fn notify_backend(&self, alert: &Alert) -> bool {
        let url = format!("{}/api/v1/alerts", self.backend_url);

        let payload = json!({
            "alert_id":    alert.alert_id,
            "patient_id":  alert.patient_id,
            "alert_type":  alert.alert_type,
            "severity":    alert.severity.to_string(),
            "message":     alert.message,
            "vitals": {
                "heart_rate":       alert.vitals_snapshot.heart_rate,
                "systolic_bp":      alert.vitals_snapshot.systolic_bp,
                "diastolic_bp":     alert.vitals_snapshot.diastolic_bp,
                "spo2":             alert.vitals_snapshot.spo2,
                "respiratory_rate": alert.vitals_snapshot.respiratory_rate,
                "temperature":      alert.vitals_snapshot.temperature,
                "glucose":          alert.vitals_snapshot.glucose,
                "lactate":          alert.vitals_snapshot.lactate,
            },
            "triggered_at": alert.triggered_at,
            "acknowledged": false,
        });

        match self.http.post(&url).json(&payload).send().await {
            Ok(resp) if resp.status().is_success() => {
                info!(
                    alert_id   = %alert.alert_id,
                    patient_id = %alert.patient_id,
                    alert_type = %alert.alert_type,
                    "Alert posted to backend"
                );
                true
            }
            Ok(resp) => {
                warn!(
                    status     = %resp.status(),
                    alert_id   = %alert.alert_id,
                    "Backend returned non-2xx for alert"
                );
                false
            }
            Err(e) => {
                error!(error = %e, alert_id = %alert.alert_id, "Failed to POST alert to backend");
                false
            }
        }
    }

    /// Send a critical alert via WebSocket broadcast (calls backend SSE endpoint)
    pub async fn broadcast_critical(&self, alert: &Alert) {
        let url = format!("{}/api/v1/alerts/broadcast", self.backend_url);

        let payload = json!({
            "alert_id":   alert.alert_id,
            "patient_id": alert.patient_id,
            "severity":   alert.severity.to_string(),
            "message":    alert.message,
        });

        if let Err(e) = self.http.post(&url).json(&payload).send().await {
            warn!(error = %e, "Failed to broadcast critical alert");
        }
    }
}
