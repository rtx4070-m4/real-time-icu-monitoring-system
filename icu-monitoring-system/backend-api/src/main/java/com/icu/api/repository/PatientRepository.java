package com.icu.api.repository;

import com.icu.api.model.Patient;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.stereotype.Repository;

import java.util.List;
import java.util.Optional;

@Repository
public interface PatientRepository extends JpaRepository<Patient, Long> {

    Optional<Patient> findByPatientId(String patientId);

    List<Patient> findByActiveTrue();

    List<Patient> findByActiveTrueOrderByPriorityAscSeverityDesc();

    List<Patient> findBySeverity(Patient.Severity severity);

    @Query("SELECT p FROM Patient p WHERE p.active = true AND p.severity IN " +
           "('CRITICAL', 'CODE_BLUE') ORDER BY p.priority ASC")
    List<Patient> findCriticalPatients();

    boolean existsByPatientId(String patientId);

    boolean existsByBedNumber(Integer bedNumber);

    @Query("SELECT COUNT(p) FROM Patient p WHERE p.active = true")
    long countActivePatients();
}
