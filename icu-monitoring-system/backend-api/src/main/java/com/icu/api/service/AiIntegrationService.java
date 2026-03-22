package com.icu.api.service;

import com.icu.api.dto.VitalsUpdateDto;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

import java.time.Duration;
import java.util.Map;
import java.util.concurrent.CompletableFuture;

/**
 * Async HTTP client that calls the Python AI module for risk prediction
 * and the Julia module for Kalman-filtered vitals.
 */
@Service
@RequiredArgsConstructor
@Slf4j
public class AiIntegrationService {

    private final WebClient.Builder webClientBuilder;

    @Value("${ai.python.url:http://ai-python:8082}")
    private String pythonAiUrl;

    @Value("${ai.julia.url:http://ai-julia:8084}")
    private String juliaAiUrl;

    public record RiskResult(double riskScore, String riskCategory, Double predictedHours) {}
    public record KalmanResult(Map<String, Double> smoothed) {}

    /**
     * Call the Python AI module asynchronously for deterioration risk scoring.
     * Returns a CompletableFuture so the caller is not blocked.
     */
    public CompletableFuture<RiskResult> getRiskScore(VitalsUpdateDto dto) {
        WebClient client = webClientBuilder.baseUrl(pythonAiUrl).build();

        Map<String, Object> payload = Map.of(
            "patient_id",       dto.getPatientId(),
            "heart_rate",       dto.getHeartRate(),
            "systolic_bp",      dto.getSystolicBp(),
            "diastolic_bp",     dto.getDiastolicBp(),
            "spo2",             dto.getSpo2(),
            "respiratory_rate", dto.getRespiratoryRate(),
            "temperature",      dto.getTemperature(),
            "glucose",          dto.getGlucose(),
            "lactate",          dto.getLactate()
        );

        return client.post()
            .uri("/api/v1/predict")
            .bodyValue(payload)
            .retrieve()
            .bodyToMono(Map.class)
            .timeout(Duration.ofSeconds(3))
            .map(resp -> new RiskResult(
                toDouble(resp.get("deterioration_risk")),
                String.valueOf(resp.get("risk_category")),
                resp.get("predicted_event_hours") != null
                    ? toDouble(resp.get("predicted_event_hours"))
                    : null
            ))
            .onErrorResume(e -> {
                log.debug("AI risk scoring unavailable for {}: {}", dto.getPatientId(), e.getMessage());
                return Mono.empty();
            })
            .toFuture();
    }

    /**
     * Call the Julia Kalman filter module asynchronously for smoothed vitals.
     */
    public CompletableFuture<KalmanResult> getKalmanSmoothed(VitalsUpdateDto dto) {
        WebClient client = webClientBuilder.baseUrl(juliaAiUrl).build();

        Map<String, Object> payload = Map.of(
            "patient_id",       dto.getPatientId(),
            "heart_rate",       dto.getHeartRate(),
            "systolic_bp",      dto.getSystolicBp(),
            "diastolic_bp",     dto.getDiastolicBp(),
            "spo2",             dto.getSpo2(),
            "respiratory_rate", dto.getRespiratoryRate(),
            "temperature",      dto.getTemperature(),
            "glucose",          dto.getGlucose(),
            "lactate",          dto.getLactate()
        );

        return client.post()
            .uri("/api/v1/kalman")
            .bodyValue(payload)
            .retrieve()
            .bodyToMono(Map.class)
            .timeout(Duration.ofSeconds(3))
            .map(resp -> {
                @SuppressWarnings("unchecked")
                Map<String, Object> smoothed = (Map<String, Object>) resp.get("smoothed");
                Map<String, Double> result = Map.of(
                    "heart_rate",       toDouble(smoothed.get("heart_rate")),
                    "systolic_bp",      toDouble(smoothed.get("systolic_bp")),
                    "spo2",             toDouble(smoothed.get("spo2")),
                    "respiratory_rate", toDouble(smoothed.get("respiratory_rate")),
                    "temperature",      toDouble(smoothed.get("temperature")),
                    "lactate",          toDouble(smoothed.get("lactate"))
                );
                return new KalmanResult(result);
            })
            .onErrorResume(e -> {
                log.debug("Kalman service unavailable for {}: {}", dto.getPatientId(), e.getMessage());
                return Mono.empty();
            })
            .toFuture();
    }

    private double toDouble(Object o) {
        if (o == null) return 0.0;
        if (o instanceof Number n) return n.doubleValue();
        try { return Double.parseDouble(o.toString()); }
        catch (NumberFormatException e) { return 0.0; }
    }
}
