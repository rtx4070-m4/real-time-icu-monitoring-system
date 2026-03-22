package com.icu.api.service;

import com.icu.api.dto.PatientDto;
import com.icu.api.dto.VitalsUpdateDto;
import com.icu.api.model.Patient;
import com.icu.api.model.VitalRecord;
import com.icu.api.repository.PatientRepository;
import com.icu.api.repository.VitalRecordRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.data.domain.PageRequest;
import org.springframework.messaging.simp.SimpMessagingTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.List;
import java.util.Optional;

@Service
@RequiredArgsConstructor
@Slf4j
@Transactional
public class PatientService {

    private final PatientRepository    patientRepository;
    private final VitalRecordRepository vitalRecordRepository;
    private final SimpMessagingTemplate websocket;
    private final AiIntegrationService  aiService;

    // ── CRUD ─────────────────────────────────────────────────────────────────

    public Patient admitPatient(PatientDto dto) {
        if (patientRepository.existsByPatientId(dto.getPatientId())) {
            throw new IllegalArgumentException("Patient already exists: " + dto.getPatientId());
        }
        if (patientRepository.existsByBedNumber(dto.getBedNumber())) {
            throw new IllegalArgumentException("Bed already occupied: " + dto.getBedNumber());
        }

        Patient patient = Patient.builder()
            .patientId(dto.getPatientId())
            .name(dto.getName())
            .age(dto.getAge())
            .diagnosis(dto.getDiagnosis())
            .bedNumber(dto.getBedNumber())
            .priority(dto.getPriority() != null ? dto.getPriority() : 5)
            .attendingPhysician(dto.getAttendingPhysician())
            .notes(dto.getNotes())
            .admissionTime(Instant.now())
            .active(true)
            .severity(Patient.Severity.STABLE)
            .build();

        Patient saved = patientRepository.save(patient);
        log.info("Patient admitted: {} ({})", saved.getPatientId(), saved.getName());

        // Notify dashboard via WebSocket
        websocket.convertAndSend("/topic/patients", saved);
        return saved;
    }

    @Transactional(readOnly = true)
    public List<Patient> getAllActivePatients() {
        return patientRepository.findByActiveTrueOrderByPriorityAscSeverityDesc();
    }

    @Transactional(readOnly = true)
    public Optional<Patient> getPatient(String patientId) {
        return patientRepository.findByPatientId(patientId);
    }

    @Transactional(readOnly = true)
    public List<Patient> getCriticalPatients() {
        return patientRepository.findCriticalPatients();
    }

    public Patient dischargePatient(String patientId) {
        Patient patient = patientRepository.findByPatientId(patientId)
            .orElseThrow(() -> new IllegalArgumentException("Patient not found: " + patientId));
        patient.setActive(false);
        Patient saved = patientRepository.save(patient);

        log.info("Patient discharged: {}", patientId);
        websocket.convertAndSend("/topic/patients", saved);
        return saved;
    }

    // ── Vitals processing ─────────────────────────────────────────────────────

    /**
     * Ingest a vitals update from Kafka (published by the C++ core engine).
     * 1. Persist vital record
     * 2. Update patient severity
     * 3. Call AI service for risk scoring
     * 4. Push update to WebSocket subscribers
     */
    public void processVitalsUpdate(VitalsUpdateDto dto) {
        Patient patient = patientRepository.findByPatientId(dto.getPatientId())
            .orElse(null);

        if (patient == null) {
            log.warn("Vitals update for unknown patient: {}", dto.getPatientId());
            return;
        }

        // Build VitalRecord
        VitalRecord record = VitalRecord.builder()
            .patientId(dto.getPatientId())
            .heartRate(dto.getHeartRate())
            .systolicBp(dto.getSystolicBp())
            .diastolicBp(dto.getDiastolicBp())
            .spo2(dto.getSpo2())
            .respiratoryRate(dto.getRespiratoryRate())
            .temperature(dto.getTemperature())
            .glucose(dto.getGlucose())
            .lactate(dto.getLactate())
            .severity(mapSeverity(dto.getSeverity()))
            .news2Score(computeNews2(dto))
            .timestamp(dto.getTimestamp() != null ? dto.getTimestamp() : Instant.now())
            .build();

        // Async AI risk scoring
        aiService.getRiskScore(dto).thenAccept(result -> {
            if (result != null) {
                record.setAiRiskScore(result.riskScore());
                record.setAiRiskCategory(result.riskCategory());
            }
        });

        VitalRecord saved = vitalRecordRepository.save(record);

        // Update patient severity + latest vitals reference
        patient.setSeverity(record.getSeverity());
        patient.setPriority(severityToPriority(record.getSeverity()));
        patient.setLatestVitals(saved);
        patientRepository.save(patient);

        // Broadcast via WebSocket
        websocket.convertAndSend("/topic/vitals/" + dto.getPatientId(), record);
        websocket.convertAndSend("/topic/dashboard", buildDashboardUpdate(patient, record));

        log.debug("Vitals saved for {} – SpO2={} HR={} Severity={}",
            dto.getPatientId(), dto.getSpo2(), dto.getHeartRate(), record.getSeverity());
    }

    @Transactional(readOnly = true)
    public List<VitalRecord> getVitalsHistory(String patientId, int hours) {
        Instant from = Instant.now().minus(hours, ChronoUnit.HOURS);
        return vitalRecordRepository
            .findByPatientIdAndTimestampBetweenOrderByTimestampAsc(patientId, from, Instant.now());
    }

    @Transactional(readOnly = true)
    public List<VitalRecord> getRecentVitals(String patientId, int count) {
        return vitalRecordRepository
            .findByPatientIdOrderByTimestampDesc(patientId, PageRequest.of(0, count));
    }

    // ── Helpers ────────────────────────────────────────────────────────────────

    private Patient.Severity mapSeverity(Integer code) {
        if (code == null) return Patient.Severity.STABLE;
        return switch (code) {
            case 0  -> Patient.Severity.STABLE;
            case 1  -> Patient.Severity.ELEVATED;
            case 2  -> Patient.Severity.CRITICAL;
            default -> Patient.Severity.CODE_BLUE;
        };
    }

    private int severityToPriority(Patient.Severity severity) {
        return switch (severity) {
            case CODE_BLUE -> 1;
            case CRITICAL  -> 2;
            case ELEVATED  -> 3;
            case STABLE    -> 5;
        };
    }

    private int computeNews2(VitalsUpdateDto v) {
        int score = 0;
        double rr = v.getRespiratoryRate();
        double sp = v.getSpo2();
        double sb = v.getSystolicBp();
        double hr = v.getHeartRate();
        double t  = v.getTemperature();
        double la = v.getLactate();

        if (rr <= 8)        score += 3; else if (rr <= 11) score += 1;
        else if (rr > 24)   score += 3; else if (rr > 20)  score += 2;
        if (sp <= 91)       score += 3; else if (sp <= 93) score += 2;
        else if (sp <= 95)  score += 1;
        if (sb <= 90)       score += 3; else if (sb <= 100) score += 2;
        else if (sb <= 110) score += 1; else if (sb > 219)  score += 3;
        if (hr <= 40)       score += 3; else if (hr <= 50)  score += 1;
        else if (hr > 130)  score += 3; else if (hr > 110)  score += 2;
        else if (hr > 90)   score += 1;
        if (t <= 35.0)      score += 3; else if (t <= 36.0) score += 1;
        else if (t > 39.0)  score += 2; else if (t > 38.0)  score += 1;
        if (la > 4.0)       score += 3; else if (la > 2.0)  score += 1;

        return score;
    }

    private Object buildDashboardUpdate(Patient patient, VitalRecord record) {
        return new Object() {
            public final String   patientId  = patient.getPatientId();
            public final String   name       = patient.getName();
            public final int      bedNumber  = patient.getBedNumber();
            public final String   severity   = patient.getSeverity().name();
            public final double   heartRate  = record.getHeartRate();
            public final double   spo2       = record.getSpo2();
            public final double   systolicBp = record.getSystolicBp();
            public final int      news2      = record.getNews2Score();
            public final Instant  timestamp  = record.getTimestamp();
        };
    }
}
