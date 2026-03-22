// src/consumer.rs – Kafka consumer for vitals stream

use crate::types::VitalsMessage;
use rdkafka::config::ClientConfig;
use rdkafka::consumer::{CommitMode, Consumer, StreamConsumer};
use rdkafka::message::Message;
use std::time::Duration;
use tracing::{error, info, warn};

/// Build a Kafka StreamConsumer
pub fn create_consumer(brokers: &str, group_id: &str, topic: &str) -> StreamConsumer {
    let consumer: StreamConsumer = ClientConfig::new()
        .set("group.id", group_id)
        .set("bootstrap.servers", brokers)
        .set("auto.offset.reset", "latest")
        .set("enable.auto.commit", "false")
        .set("session.timeout.ms", "6000")
        .set("socket.timeout.ms", "6000")
        .set("fetch.wait.max.ms", "100")
        .create()
        .expect("Failed to create Kafka consumer");

    consumer
        .subscribe(&[topic])
        .expect("Failed to subscribe to Kafka topic");

    info!(brokers, group_id, topic, "Kafka consumer created and subscribed");
    consumer
}

/// Parse a raw Kafka message payload into VitalsMessage
pub fn parse_vitals_message(payload: &[u8]) -> Option<VitalsMessage> {
    match serde_json::from_slice::<VitalsMessage>(payload) {
        Ok(v) => Some(v),
        Err(e) => {
            warn!(error = %e, "Failed to parse vitals message");
            None
        }
    }
}
