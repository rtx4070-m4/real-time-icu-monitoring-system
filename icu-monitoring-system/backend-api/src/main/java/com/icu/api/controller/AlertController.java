package com.icu.api.controller;

import com.icu.api.model.Alert;
import com.icu.api.model.Patient;
import com.icu.api.service.AlertService;
import lombok.RequiredArgsConstructor;
import org.springframework.data.domain.Page;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.*;

import java.time.Instant;
import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/api/v1/alerts")
@RequiredArgsConstructor
@CrossOrigin(origins = "*")
public class AlertController {

    private final AlertService alertService;

    /** GET /api/v1/alerts — unacknowledged alerts */
    @GetMapping
    public ResponseEntity<List<Alert>> getUnacknowledgedAlerts() {
        return ResponseEntity.ok(alertService.getUnacknowledgedAlerts());
    }

    /** GET /api/v1/alerts/critical */
    @GetMapping("/critical")
    public ResponseEntity<List<Alert>> getCriticalAlerts() {
        return ResponseEntity.ok(alertService.getCriticalUnacknowledgedAlerts());
    }

    /** GET /api/v1/alerts/summary */
    @GetMapping("/summary")
    public ResponseEntity<Map<String, Object>> getAlertSummary() {
        return ResponseEntity.ok(alertService.getAlertSummary());
    }

    /** GET /api/v1/alerts/patient/{patientId}?page=0&size=20 */
    @GetMapping("/patient/{patientId}")
    public ResponseEntity<Page<Alert>> getPatientAlerts(
        @PathVariable String patientId,
        @RequestParam(defaultValue = "0")  int page,
        @RequestParam(defaultValue = "20") int size)
    {
        return ResponseEntity.ok(alertService.getPatientAlerts(patientId, page, size));
    }

    /**
     * POST /api/v1/alerts — receive alert from Rust alert engine via REST
     * (Alternative to Kafka; supports direct HTTP push from the alert engine)
     */
    @PostMapping
    public ResponseEntity<Alert> receiveAlert(@RequestBody Map<String, Object> payload) {
        Alert alert = Alert.builder()
            .alertId(getString(payload, "alert_id", "DIRECT-" + Instant.now().toEpochMilli()))
            .patientId(getString(payload, "patient_id", "UNKNOWN"))
            .alertType(getString(payload, "alert_type", "UNKNOWN"))
            .severity(parseSeverity(getString(payload, "severity", "ELEVATED")))
            .message(getString(payload, "message", ""))
            .triggeredAt(Instant.now())
            .acknowledged(false)
            .build();

        return ResponseEntity.status(HttpStatus.CREATED).body(alertService.saveAlert(alert));
    }

    /**
     * POST /api/v1/alerts/broadcast — broadcast a critical alert (called by Rust engine)
     */
    @PostMapping("/broadcast")
    public ResponseEntity<Void> broadcastAlert(@RequestBody Map<String, Object> payload) {
        // The alert service already broadcasts via WebSocket when saving;
        // this endpoint just confirms receipt for the Rust engine.
        return ResponseEntity.ok().build();
    }

    /** PUT /api/v1/alerts/{alertId}/acknowledge */
    @PutMapping("/{alertId}/acknowledge")
    @PreAuthorize("hasAnyRole('ADMIN','PHYSICIAN','NURSE')")
    public ResponseEntity<Alert> acknowledge(
        @PathVariable String alertId,
        @RequestBody Map<String, String> body)
    {
        String by    = body.getOrDefault("acknowledgedBy", "unknown");
        String notes = body.getOrDefault("notes", "");
        return ResponseEntity.ok(alertService.acknowledgeAlert(alertId, by, notes));
    }

    // ── Helpers ───────────────────────────────────────────────────────────────

    private String getString(Map<String, Object> m, String key, String def) {
        Object v = m.get(key);
        return v != null ? v.toString() : def;
    }

    private Patient.Severity parseSeverity(String s) {
        try { return Patient.Severity.valueOf(s.toUpperCase().replace("-", "_").replace(" ", "_")); }
        catch (Exception e) { return Patient.Severity.ELEVATED; }
    }
}
