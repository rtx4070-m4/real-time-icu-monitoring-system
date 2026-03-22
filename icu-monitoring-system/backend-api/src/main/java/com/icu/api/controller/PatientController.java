package com.icu.api.controller;

import com.icu.api.dto.PatientDto;
import com.icu.api.model.Patient;
import com.icu.api.model.VitalRecord;
import com.icu.api.service.PatientService;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/api/v1/patients")
@RequiredArgsConstructor
@CrossOrigin(origins = "*")
public class PatientController {

    private final PatientService patientService;

    /** GET /api/v1/patients — list all active patients (priority-sorted) */
    @GetMapping
    public ResponseEntity<List<Patient>> getAllPatients() {
        return ResponseEntity.ok(patientService.getAllActivePatients());
    }

    /** GET /api/v1/patients/critical */
    @GetMapping("/critical")
    public ResponseEntity<List<Patient>> getCritical() {
        return ResponseEntity.ok(patientService.getCriticalPatients());
    }

    /** GET /api/v1/patients/{id} */
    @GetMapping("/{id}")
    public ResponseEntity<Patient> getPatient(@PathVariable String id) {
        return patientService.getPatient(id)
            .map(ResponseEntity::ok)
            .orElse(ResponseEntity.notFound().build());
    }

    /** POST /api/v1/patients — admit a new patient */
    @PostMapping
    @PreAuthorize("hasAnyRole('ADMIN','PHYSICIAN','NURSE')")
    public ResponseEntity<Patient> admitPatient(@Valid @RequestBody PatientDto dto) {
        Patient patient = patientService.admitPatient(dto);
        return ResponseEntity.status(HttpStatus.CREATED).body(patient);
    }

    /** DELETE /api/v1/patients/{id} — discharge patient */
    @DeleteMapping("/{id}")
    @PreAuthorize("hasAnyRole('ADMIN','PHYSICIAN')")
    public ResponseEntity<Patient> dischargePatient(@PathVariable String id) {
        return ResponseEntity.ok(patientService.dischargePatient(id));
    }

    /** GET /api/v1/patients/{id}/vitals?hours=6 */
    @GetMapping("/{id}/vitals")
    public ResponseEntity<List<VitalRecord>> getVitalsHistory(
        @PathVariable String id,
        @RequestParam(defaultValue = "6") int hours)
    {
        return ResponseEntity.ok(patientService.getVitalsHistory(id, hours));
    }

    /** GET /api/v1/patients/{id}/vitals/recent?count=50 */
    @GetMapping("/{id}/vitals/recent")
    public ResponseEntity<List<VitalRecord>> getRecentVitals(
        @PathVariable String id,
        @RequestParam(defaultValue = "50") int count)
    {
        return ResponseEntity.ok(patientService.getRecentVitals(id, count));
    }

    /** GET /api/v1/patients/stats/summary */
    @GetMapping("/stats/summary")
    public ResponseEntity<Map<String, Object>> getStatsSummary() {
        long active   = patientService.getAllActivePatients().size();
        long critical = patientService.getCriticalPatients().size();
        return ResponseEntity.ok(Map.of(
            "active_patients",   active,
            "critical_patients", critical,
            "stable_patients",   active - critical
        ));
    }
}
