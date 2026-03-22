package com.icu.api.model;

import jakarta.persistence.*;
import lombok.*;

import java.time.Instant;

/**
 * JPA entity representing one set of vital sign measurements.
 */
@Entity
@Table(name = "vital_records", indexes = {
    @Index(name = "idx_vr_patient_id", columnList = "patient_id"),
    @Index(name = "idx_vr_timestamp",  columnList = "timestamp"),
    @Index(name = "idx_vr_severity",   columnList = "severity"),
})
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class VitalRecord {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "patient_id", nullable = false, length = 20)
    private String patientId;

    @Column(name = "heart_rate", nullable = false)
    private Double heartRate;

    @Column(name = "systolic_bp", nullable = false)
    private Double systolicBp;

    @Column(name = "diastolic_bp", nullable = false)
    private Double diastolicBp;

    @Column(nullable = false)
    private Double spo2;

    @Column(name = "respiratory_rate", nullable = false)
    private Double respiratoryRate;

    @Column(nullable = false)
    private Double temperature;

    @Column(nullable = false)
    private Double glucose;

    @Column(nullable = false)
    private Double lactate;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 15)
    @Builder.Default
    private Patient.Severity severity = Patient.Severity.STABLE;

    @Column(name = "news2_score")
    private Integer news2Score;

    @Column(name = "ai_risk_score")
    private Double aiRiskScore;

    @Column(name = "ai_risk_category", length = 20)
    private String aiRiskCategory;

    @Column(nullable = false)
    @Builder.Default
    private Instant timestamp = Instant.now();
}
