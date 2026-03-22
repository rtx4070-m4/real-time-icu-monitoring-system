package com.icu.api.repository;

import com.icu.api.model.VitalRecord;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.stereotype.Repository;

import java.time.Instant;
import java.util.List;

@Repository
public interface VitalRecordRepository extends JpaRepository<VitalRecord, Long> {

    List<VitalRecord> findByPatientIdOrderByTimestampDesc(String patientId, Pageable pageable);

    List<VitalRecord> findByPatientIdAndTimestampBetweenOrderByTimestampAsc(
        String patientId, Instant from, Instant to);

    @Query("SELECT v FROM VitalRecord v WHERE v.patientId = :patientId " +
           "ORDER BY v.timestamp DESC LIMIT 1")
    VitalRecord findLatestByPatientId(String patientId);

    @Query("SELECT AVG(v.heartRate), AVG(v.spo2), AVG(v.systolicBp), AVG(v.lactate) " +
           "FROM VitalRecord v WHERE v.patientId = :patientId AND v.timestamp >= :since")
    Object[] averageVitalsSince(String patientId, Instant since);

    void deleteByPatientIdAndTimestampBefore(String patientId, Instant cutoff);
}
