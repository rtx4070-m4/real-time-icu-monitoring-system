package com.icu.api.repository;

import com.icu.api.model.Alert;
import com.icu.api.model.Patient;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.stereotype.Repository;

import java.time.Instant;
import java.util.List;
import java.util.Optional;

@Repository
public interface AlertRepository extends JpaRepository<Alert, Long> {

    Optional<Alert> findByAlertId(String alertId);

    Page<Alert> findByPatientIdOrderByTriggeredAtDesc(String patientId, Pageable pageable);

    List<Alert> findByAcknowledgedFalseOrderByTriggeredAtDesc();

    @Query("SELECT a FROM Alert a WHERE a.acknowledged = false AND a.severity IN " +
           "('CRITICAL', 'CODE_BLUE') ORDER BY a.triggeredAt DESC")
    List<Alert> findUnacknowledgedCriticalAlerts();

    List<Alert> findByPatientIdAndTriggeredAtBetween(
        String patientId, Instant from, Instant to);

    @Query("SELECT COUNT(a) FROM Alert a WHERE a.acknowledged = false")
    long countUnacknowledged();

    @Query("SELECT a.alertType, COUNT(a) FROM Alert a " +
           "WHERE a.triggeredAt >= :since GROUP BY a.alertType ORDER BY COUNT(a) DESC")
    List<Object[]> alertTypeSummary(Instant since);
}
