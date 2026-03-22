package com.icu.api.service;

import com.icu.api.model.Alert;
import com.icu.api.model.Patient;
import com.icu.api.repository.AlertRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.messaging.simp.SimpMessagingTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

@Service
@RequiredArgsConstructor
@Slf4j
@Transactional
public class AlertService {

    private final AlertRepository    alertRepository;
    private final SimpMessagingTemplate websocket;

    /**
     * Persist an incoming alert (from Rust alert engine via Kafka/REST)
     * and broadcast it to all WebSocket subscribers.
     */
    public Alert saveAlert(Alert alert) {
        Alert saved = alertRepository.save(alert);

        // Broadcast to all connected dashboard clients
        websocket.convertAndSend("/topic/alerts", saved);

        // For critical/code-blue, use a separate high-priority channel
        if (saved.getSeverity() == Patient.Severity.CODE_BLUE ||
            saved.getSeverity() == Patient.Severity.CRITICAL) {
            websocket.convertAndSend("/topic/alerts/critical", saved);
            log.warn("🚨 CRITICAL ALERT [{}] patient={} type={} msg={}",
                saved.getSeverity(), saved.getPatientId(),
                saved.getAlertType(), saved.getMessage());
        }

        return saved;
    }

    /**
     * Acknowledge an alert (mark as reviewed by a clinician).
     */
    public Alert acknowledgeAlert(String alertId, String acknowledgedBy, String notes) {
        Alert alert = alertRepository.findByAlertId(alertId)
            .orElseThrow(() -> new IllegalArgumentException("Alert not found: " + alertId));

        if (alert.getAcknowledged()) {
            log.warn("Alert {} already acknowledged", alertId);
            return alert;
        }

        alert.setAcknowledged(true);
        alert.setAcknowledgedAt(Instant.now());
        alert.setAcknowledgedBy(acknowledgedBy);
        alert.setNotes(notes);

        Alert saved = alertRepository.save(alert);
        log.info("Alert {} acknowledged by {}", alertId, acknowledgedBy);

        // Notify dashboard of acknowledgement
        websocket.convertAndSend("/topic/alerts/ack", Map.of(
            "alertId",          alertId,
            "acknowledgedBy",   acknowledgedBy,
            "acknowledgedAt",   saved.getAcknowledgedAt()
        ));

        return saved;
    }

    @Transactional(readOnly = true)
    public List<Alert> getUnacknowledgedAlerts() {
        return alertRepository.findByAcknowledgedFalseOrderByTriggeredAtDesc();
    }

    @Transactional(readOnly = true)
    public List<Alert> getCriticalUnacknowledgedAlerts() {
        return alertRepository.findUnacknowledgedCriticalAlerts();
    }

    @Transactional(readOnly = true)
    public Page<Alert> getPatientAlerts(String patientId, int page, int size) {
        return alertRepository.findByPatientIdOrderByTriggeredAtDesc(
            patientId, PageRequest.of(page, size));
    }

    @Transactional(readOnly = true)
    public Map<String, Object> getAlertSummary() {
        Instant since = Instant.now().minus(24, ChronoUnit.HOURS);
        List<Object[]> typeSummary = alertRepository.alertTypeSummary(since);

        Map<String, Long> byType = typeSummary.stream()
            .collect(Collectors.toMap(
                row -> (String) row[0],
                row -> (Long) row[1]
            ));

        return Map.of(
            "unacknowledged_count", alertRepository.countUnacknowledged(),
            "alert_types_24h",      byType,
            "critical_count",       getCriticalUnacknowledgedAlerts().size()
        );
    }
}
