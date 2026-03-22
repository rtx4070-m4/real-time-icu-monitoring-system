// src/main.rs – ICU Alert Engine entry point
// Event-driven architecture: consume Kafka vitals → evaluate rules → notify backend

mod consumer;
mod notifier;
mod rules;
mod types;

use consumer::{create_consumer, parse_vitals_message};
use notifier::AlertNotifier;
use rdkafka::consumer::{CommitMode, Consumer};
use rdkafka::message::Message;
use rules::RulesEngine;
use std::env;
use tokio::sync::mpsc;
use tracing::{error, info, warn};
use tracing_subscriber::{fmt, EnvFilter};
use types::Severity;

#[tokio::main]
async fn main() {
    // ── Logging setup ─────────────────────────────────────────────────────────
    tracing_subscriber::fmt()
        .with_env_filter(EnvFilter::from_default_env()
            .add_directive("icu_alert_engine=info".parse().unwrap()))
        .with_target(false)
        .compact()
        .init();

    info!("╔═══════════════════════════════════════════════════════╗");
    info!("║   ICU Alert Engine  –  Rust  |  Event-Driven          ║");
    info!("╚═══════════════════════════════════════════════════════╝");

    // ── Configuration ─────────────────────────────────────────────────────────
    let kafka_brokers  = env::var("KAFKA_BROKERS").unwrap_or_else(|_| "kafka:9092".into());
    let kafka_topic    = env::var("KAFKA_VITALS_TOPIC").unwrap_or_else(|_| "icu.vitals".into());
    let kafka_group    = env::var("KAFKA_GROUP_ID").unwrap_or_else(|_| "icu-alert-engine".into());
    let backend_url    = env::var("BACKEND_URL").unwrap_or_else(|_| "http://backend-api:8080".into());
    let alert_topic    = env::var("KAFKA_ALERTS_TOPIC").unwrap_or_else(|_| "icu.alerts".into());

    info!(kafka_brokers, kafka_topic, backend_url, "Configuration loaded");

    // ── Components ────────────────────────────────────────────────────────────
    let consumer = create_consumer(&kafka_brokers, &kafka_group, &kafka_topic);
    let engine   = RulesEngine::new();
    let notifier = AlertNotifier::new(&backend_url, &alert_topic);

    // ── Alert dispatch channel ────────────────────────────────────────────────
    let (alert_tx, mut alert_rx) = mpsc::channel::<types::Alert>(1024);

    // Alert dispatch task – sends alerts to backend asynchronously
    let notifier_handle = {
        tokio::spawn(async move {
            while let Some(alert) = alert_rx.recv().await {
                notifier.notify_backend(&alert).await;

                // Broadcast critical/code-blue alerts immediately
                if alert.severity >= Severity::Critical {
                    notifier.broadcast_critical(&alert).await;
                }
            }
        })
    };

    // ── Main consumer loop ────────────────────────────────────────────────────
    info!("Listening for vitals on topic '{}'...", kafka_topic);

    loop {
        match consumer.recv().await {
            Err(e) => {
                error!(error = %e, "Kafka receive error");
                tokio::time::sleep(tokio::time::Duration::from_millis(500)).await;
            }
            Ok(msg) => {
                let payload = match msg.payload() {
                    Some(p) => p,
                    None => {
                        warn!("Empty Kafka message payload, skipping");
                        continue;
                    }
                };

                if let Some(vitals) = parse_vitals_message(payload) {
                    let alerts = engine.evaluate(&vitals);

                    for alert in alerts {
                        if let Err(e) = alert_tx.send(alert).await {
                            error!(error = %e, "Alert channel send failed");
                        }
                    }
                }

                // Commit offset after successful processing
                if let Err(e) = consumer.commit_message(&msg, CommitMode::Async) {
                    warn!(error = %e, "Failed to commit Kafka offset");
                }
            }
        }
    }
}
