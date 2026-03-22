package com.icu.api.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.Data;
import java.time.Instant;

/**
 * DTO for vitals messages arriving from Kafka (C++ core engine JSON format).
 */
@Data
public class VitalsUpdateDto {

    @JsonProperty("patient_id")
    private String patientId;

    @JsonProperty("heart_rate")
    private Double heartRate;

    @JsonProperty("systolic_bp")
    private Double systolicBp;

    @JsonProperty("diastolic_bp")
    private Double diastolicBp;

    @JsonProperty("spo2")
    private Double spo2;

    @JsonProperty("respiratory_rate")
    private Double respiratoryRate;

    @JsonProperty("temperature")
    private Double temperature;

    @JsonProperty("glucose")
    private Double glucose;

    @JsonProperty("lactate")
    private Double lactate;

    @JsonProperty("severity")
    private Integer severity;

    @JsonProperty("timestamp")
    private Instant timestamp;
}
