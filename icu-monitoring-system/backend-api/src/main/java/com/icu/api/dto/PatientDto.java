package com.icu.api.dto;

import jakarta.validation.constraints.*;
import lombok.Data;
import java.time.Instant;

// ── Patient DTO ───────────────────────────────────────────────────────────────
@Data
public class PatientDto {
    @NotBlank
    @Size(max = 20)
    private String patientId;

    @NotBlank
    @Size(max = 100)
    private String name;

    @NotNull @Min(0) @Max(130)
    private Integer age;

    @NotBlank
    private String diagnosis;

    @NotNull @Min(1)
    private Integer bedNumber;

    @Min(1) @Max(5)
    private Integer priority;

    @Size(max = 100)
    private String attendingPhysician;

    @Size(max = 500)
    private String notes;
}
