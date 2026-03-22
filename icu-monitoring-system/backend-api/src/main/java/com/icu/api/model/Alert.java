package com.icu.api.model;

import jakarta.persistence.*;
import lombok.*;
import org.hibernate.annotations.CreationTimestamp;

import java.time.Instant;

@Entity
@Table(name = "alerts", indexes = {
    @Index(name = "idx_alert_patient_id",  columnList = "patient_id"),
    @Index(name = "idx_alert_triggered_at", columnList = "triggered_at"),
    @Index(name = "idx_alert_severity",    columnList = "severity"),
    @Index(name = "idx_alert_acknowledged",columnList = "acknowledged"),
})
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class Alert {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "alert_id", unique = true, nullable = false, length = 50)
    private String alertId;

    @Column(name = "patient_id", nullable = false, length = 20)
    private String patientId;

    @Column(name = "alert_type", nullable = false, length = 50)
    private String alertType;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 15)
    private Patient.Severity severity;

    @Column(nullable = false, length = 500)
    private String message;

    // Vitals snapshot at time of alert
    @Column(name = "vitals_hr")   private Double vitalsHr;
    @Column(name = "vitals_sbp")  private Double vitalsSbp;
    @Column(name = "vitals_dbp")  private Double vitalsDbp;
    @Column(name = "vitals_spo2") private Double vitalsSpo2;
    @Column(name = "vitals_rr")   private Double vitalsRr;
    @Column(name = "vitals_temp") private Double vitalsTemp;
    @Column(name = "vitals_lac")  private Double vitalsLac;

    @Column(name = "triggered_at", nullable = false)
    private Instant triggeredAt;

    @Column(nullable = false)
    @Builder.Default
    private Boolean acknowledged = false;

    @Column(name = "acknowledged_at")
    private Instant acknowledgedAt;

    @Column(name = "acknowledged_by", length = 100)
    private String acknowledgedBy;

    @Column(length = 500)
    private String notes;

    @CreationTimestamp
    @Column(name = "created_at", updatable = false)
    private Instant createdAt;
}
