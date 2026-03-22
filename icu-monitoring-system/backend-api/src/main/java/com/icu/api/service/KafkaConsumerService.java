package com.icu.api.service;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.icu.api.dto.VitalsUpdateDto;
import com.icu.api.model.Alert;
import com.icu.api.model.Patient;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.support.Acknowledgment;
import org.springframework.stereotype.Service;

import java.time.Instant;
import java.util.Map;

/**
 * Kafka consumer: bridges the message bus to the service layer.
 * Consumes from icu.vitals (C++ core engine) and icu.alerts (Rust alert engine).
 */
@Service
@RequiredArgsConstructor
@Slf4j
public class KafkaConsumerService {

    private final PatientService patientService;
    private final AlertService   alertService;
    private final ObjectMapper   objectMapper;

    /**
     * Consume vitals messages from the C++ core engine.
     */
    @KafkaListener(
        topics   = "${kafka.topics.vitals:icu.vitals}",
        groupId  = "${kafka.consumer.group-id:icu-backend}",
        containerFactory = "kafkaListenerContainerFactory"
    )
    public void consumeVitals(ConsumerRecord<String, String> record, Acknowledgment ack) {
        try {
            VitalsUpdateDto dto = objectMapper.readValue(record.value(), VitalsUpdateDto.class);
            patientService.processVitalsUpdate(dto);
            ack.acknowledge();

        } catch (Exception e) {
            log.error("Failed to process vitals message [offset={}]: {}",
                record.offset(), e.getMessage(), e);
            // Don't re-queue — log and continue (dead-letter handling can be added)
            ack.acknowledge();
        }
    }

    /**
     * Consume alert messages from the Rust alert engine.
     */
    @KafkaListener(
        topics   = "${kafka.topics.alerts:icu.alerts}",
        groupId  = "${kafka.consumer.group-id:icu-backend}",
        containerFactory = "kafkaListenerContainerFactory"
    )
    public void consumeAlerts(ConsumerRecord<String, String> record, Acknowledgment ack) {
        try {
            @SuppressWarnings("unchecked")
            Map<String, Object> payload = objectMapper.readValue(record.value(), Map.class);

            Alert alert = Alert.builder()
                .alertId(getString(payload, "alert_id", "UNKNOWN-" + Instant.now().toEpochMilli()))
                .patientId(getString(payload, "patient_id", "UNKNOWN"))
                .alertType(getString(payload, "alert_type", "UNKNOWN"))
                .severity(parseSeverity(getString(payload, "severity", "ELEVATED")))
                .message(getString(payload, "message", ""))
                .triggeredAt(Instant.now())
                .acknowledged(false)
                .build();

            // Extract vitals snapshot if present
            @SuppressWarnings("unchecked")
            Map<String, Object> vitals = (Map<String, Object>) payload.get("vitals");
            if (vitals != null) {
                alert.setVitalsHr(toDouble(vitals.get("heart_rate")));
                alert.setVitalsSbp(toDouble(vitals.get("systolic_bp")));
                alert.setVitalsDbp(toDouble(vitals.get("diastolic_bp")));
                alert.setVitalsSpo2(toDouble(vitals.get("spo2")));
                alert.setVitalsRr(toDouble(vitals.get("respiratory_rate")));
                alert.setVitalsTemp(toDouble(vitals.get("temperature")));
                alert.setVitalsLac(toDouble(vitals.get("lactate")));
            }

            alertService.saveAlert(alert);
            ack.acknowledge();

        } catch (Exception e) {
            log.error("Failed to process alert message [offset={}]: {}",
                record.offset(), e.getMessage(), e);
            ack.acknowledge();
        }
    }

    // ── Helpers ───────────────────────────────────────────────────────────────

    private String getString(Map<String, Object> map, String key, String defaultValue) {
        Object val = map.get(key);
        return val != null ? val.toString() : defaultValue;
    }

    private double toDouble(Object o) {
        if (o == null) return 0.0;
        if (o instanceof Number n) return n.doubleValue();
        try { return Double.parseDouble(o.toString()); }
        catch (NumberFormatException e) { return 0.0; }
    }

    private Patient.Severity parseSeverity(String s) {
        try { return Patient.Severity.valueOf(s.toUpperCase().replace(" ", "_")); }
        catch (Exception e) { return Patient.Severity.ELEVATED; }
    }
}
