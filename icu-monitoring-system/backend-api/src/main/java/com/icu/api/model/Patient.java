package com.icu.api.model;

import jakarta.persistence.*;
import jakarta.validation.constraints.*;
import lombok.*;
import org.hibernate.annotations.CreationTimestamp;
import org.hibernate.annotations.UpdateTimestamp;

import java.time.Instant;
import java.util.List;

/**
 * JPA entity representing an ICU patient.
 */
@Entity
@Table(name = "patients", indexes = {
    @Index(name = "idx_patient_id",   columnList = "patient_id",  unique = true),
    @Index(name = "idx_bed_number",   columnList = "bed_number"),
    @Index(name = "idx_active",       columnList = "active"),
})
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class Patient {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "patient_id", unique = true, nullable = false, length = 20)
    @NotBlank
    private String patientId;

    @Column(nullable = false, length = 100)
    @NotBlank
    @Size(max = 100)
    private String name;

    @Column(nullable = false)
    @Min(0) @Max(130)
    private Integer age;

    @Column(nullable = false, length = 50)
    @NotBlank
    private String diagnosis;

    @Column(name = "bed_number", nullable = false)
    @Min(1)
    private Integer bedNumber;

    @Column(nullable = false)
    @Min(1) @Max(5)
    @Builder.Default
    private Integer priority = 5;

    @Column(nullable = false)
    @Builder.Default
    private Boolean active = true;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 15)
    @Builder.Default
    private Severity severity = Severity.STABLE;

    @Column(name = "admission_time", nullable = false)
    @Builder.Default
    private Instant admissionTime = Instant.now();

    @Column(length = 500)
    private String notes;

    @Column(name = "attending_physician", length = 100)
    private String attendingPhysician;

    @CreationTimestamp
    @Column(name = "created_at", updatable = false)
    private Instant createdAt;

    @UpdateTimestamp
    @Column(name = "updated_at")
    private Instant updatedAt;

    // Latest vitals snapshot (denormalised for fast dashboard reads)
    @OneToOne(cascade = CascadeType.ALL, fetch = FetchType.EAGER, orphanRemoval = true)
    @JoinColumn(name = "latest_vitals_id")
    private VitalRecord latestVitals;

    public enum Severity {
        STABLE, ELEVATED, CRITICAL, CODE_BLUE
    }
}
