#include "vitals_simulator.hpp"
#include <algorithm>
#include <cmath>
#include <stdexcept>

namespace icu {

VitalsSimulator::VitalsSimulator()
    : rng_(std::random_device{}()),
      noise_(0.0, 1.0) {}

// Generate physiologically plausible starting vitals based on age/diagnosis
VitalSigns VitalsSimulator::generate_initial_vitals(int age,
                                                     const std::string& diagnosis) {
    VitalSigns v{};
    v.timestamp = std::chrono::system_clock::now();

    // Baseline values
    v.heart_rate       = 75.0 + (age > 65 ? 5.0 : 0.0);
    v.systolic_bp      = 120.0 + (age - 40) * 0.3;
    v.diastolic_bp     = 80.0  + (age - 40) * 0.15;
    v.spo2             = 97.5;
    v.respiratory_rate = 16.0;
    v.temperature      = 36.8;
    v.glucose          = 90.0 + (age > 60 ? 15.0 : 0.0);
    v.lactate          = 1.0;

    // Adjust by diagnosis
    if (diagnosis == "SEPSIS") {
        v.heart_rate       += 25.0;
        v.temperature      += 1.5;
        v.respiratory_rate += 6.0;
        v.spo2             -= 4.0;
        v.lactate          += 2.5;
        v.systolic_bp      -= 20.0;
    } else if (diagnosis == "CARDIAC_FAILURE") {
        v.heart_rate       += 20.0;
        v.spo2             -= 5.0;
        v.systolic_bp      -= 15.0;
        v.diastolic_bp     -= 8.0;
        v.respiratory_rate += 4.0;
    } else if (diagnosis == "RESPIRATORY_FAILURE") {
        v.spo2             -= 8.0;
        v.respiratory_rate += 10.0;
        v.heart_rate       += 15.0;
        v.lactate          += 1.5;
    } else if (diagnosis == "STROKE") {
        v.systolic_bp      += 30.0;
        v.diastolic_bp     += 15.0;
        v.heart_rate       += 10.0;
    } else if (diagnosis == "TRAUMA") {
        v.heart_rate       += 30.0;
        v.systolic_bp      -= 25.0;
        v.spo2             -= 3.0;
        v.lactate          += 3.0;
        v.respiratory_rate += 8.0;
    }

    v.severity = compute_severity(v);
    return clamp_vitals(v);
}

VitalSigns VitalsSimulator::update_vitals(const VitalSigns& current,
                                           double hr_trend,
                                           double bp_trend,
                                           double spo2_trend,
                                           double rr_trend,
                                           double temp_trend) {
    VitalSigns v = current;
    v.timestamp  = std::chrono::system_clock::now();

    // Apply trend + physiological noise (each vital has realistic variance)
    v.heart_rate       += hr_trend   + hr_noise();
    v.systolic_bp      += bp_trend   + bp_noise();
    v.diastolic_bp     += bp_trend * 0.6 + bp_noise() * 0.6;
    v.spo2             += spo2_trend + spo2_noise();
    v.respiratory_rate += rr_trend   + rr_noise();
    v.temperature      += temp_trend + temp_noise();
    v.glucose          += glucose_noise();
    v.lactate          += lactate_noise();

    // Physiological coupling: low SpO2 raises HR and RR
    if (v.spo2 < 92.0) {
        double hypoxia_drive = (92.0 - v.spo2) * 0.5;
        v.heart_rate       += hypoxia_drive;
        v.respiratory_rate += hypoxia_drive * 0.3;
        v.lactate          += 0.05;
    }

    // Fever drives HR up (each degree above 37 adds ~7 bpm)
    if (v.temperature > 37.0) {
        v.heart_rate += (v.temperature - 37.0) * 7.0 * noise_(rng_) * 0.2;
    }

    // Hypertensive crisis modelling
    if (v.systolic_bp > 180.0) {
        v.heart_rate += 5.0 * noise_(rng_);
    }

    v.severity = compute_severity(v);
    return clamp_vitals(v);
}

// NEWS2-style scoring (National Early Warning Score 2)
Severity VitalsSimulator::compute_severity(const VitalSigns& v) {
    int score = compute_news2_score(v);

    if (score >= 7)       return Severity::CODE_BLUE;
    else if (score >= 5)  return Severity::CRITICAL;
    else if (score >= 3)  return Severity::ELEVATED;
    else                  return Severity::STABLE;
}

int VitalsSimulator::compute_news2_score(const VitalSigns& v) {
    int score = 0;

    // Respiratory rate
    if      (v.respiratory_rate <= 8)               score += 3;
    else if (v.respiratory_rate <= 11)              score += 1;
    else if (v.respiratory_rate <= 20)              score += 0;
    else if (v.respiratory_rate <= 24)              score += 2;
    else                                            score += 3;

    // SpO2
    if      (v.spo2 <= 91)                          score += 3;
    else if (v.spo2 <= 93)                          score += 2;
    else if (v.spo2 <= 95)                          score += 1;
    else                                            score += 0;

    // Systolic BP
    if      (v.systolic_bp <= 90)                   score += 3;
    else if (v.systolic_bp <= 100)                  score += 2;
    else if (v.systolic_bp <= 110)                  score += 1;
    else if (v.systolic_bp <= 219)                  score += 0;
    else                                            score += 3;

    // Heart rate
    if      (v.heart_rate <= 40)                    score += 3;
    else if (v.heart_rate <= 50)                    score += 1;
    else if (v.heart_rate <= 90)                    score += 0;
    else if (v.heart_rate <= 110)                   score += 1;
    else if (v.heart_rate <= 130)                   score += 2;
    else                                            score += 3;

    // Temperature
    if      (v.temperature <= 35.0)                 score += 3;
    else if (v.temperature <= 36.0)                 score += 1;
    else if (v.temperature <= 38.0)                 score += 0;
    else if (v.temperature <= 39.0)                 score += 1;
    else                                            score += 2;

    // Lactate (bonus scoring)
    if      (v.lactate > 4.0)                       score += 3;
    else if (v.lactate > 2.0)                       score += 1;

    return score;
}

void VitalsSimulator::apply_deterioration_event(PatientState& patient) {
    // Sudden physiological decompensation event
    std::lock_guard<std::mutex> lk(patient.vitals_mutex);

    std::uniform_real_distribution<double> type_dist(0.0, 1.0);
    double event_type = type_dist(rng_);

    if (event_type < 0.25) {
        // Hypoxic episode
        patient.current_vitals.spo2        -= 8.0;
        patient.current_vitals.heart_rate  += 20.0;
        patient.current_vitals.respiratory_rate += 10.0;
        patient.spo2_trend = -0.3;
        patient.hr_trend   =  0.5;
    } else if (event_type < 0.50) {
        // Hypotensive shock
        patient.current_vitals.systolic_bp  -= 30.0;
        patient.current_vitals.heart_rate   += 30.0;
        patient.current_vitals.lactate      += 2.0;
        patient.bp_trend  = -0.8;
        patient.hr_trend  =  0.8;
    } else if (event_type < 0.75) {
        // Septic deterioration
        patient.current_vitals.temperature  += 1.5;
        patient.current_vitals.heart_rate   += 25.0;
        patient.current_vitals.respiratory_rate += 8.0;
        patient.current_vitals.lactate      += 1.5;
        patient.temp_trend = 0.05;
        patient.hr_trend   = 0.4;
    } else {
        // Cardiac event
        patient.current_vitals.heart_rate   += 40.0;
        patient.current_vitals.systolic_bp  -= 20.0;
        patient.current_vitals.spo2         -= 5.0;
        patient.hr_trend  =  1.0;
        patient.bp_trend  = -0.5;
    }

    patient.deteriorating.store(true);
}

VitalSigns VitalsSimulator::clamp_vitals(const VitalSigns& v) const {
    VitalSigns c = v;
    c.heart_rate       = std::clamp(c.heart_rate,       20.0, 220.0);
    c.systolic_bp      = std::clamp(c.systolic_bp,      50.0, 260.0);
    c.diastolic_bp     = std::clamp(c.diastolic_bp,     30.0, 160.0);
    c.spo2             = std::clamp(c.spo2,             70.0, 100.0);
    c.respiratory_rate = std::clamp(c.respiratory_rate,  4.0,  50.0);
    c.temperature      = std::clamp(c.temperature,      34.0,  42.5);
    c.glucose          = std::clamp(c.glucose,          40.0, 500.0);
    c.lactate          = std::clamp(c.lactate,           0.3,  15.0);
    return c;
}

// Noise generators with physiologically appropriate variance
double VitalsSimulator::hr_noise()      { return noise_(rng_) * 1.5; }
double VitalsSimulator::bp_noise()      { return noise_(rng_) * 2.0; }
double VitalsSimulator::spo2_noise()    { return noise_(rng_) * 0.3; }
double VitalsSimulator::rr_noise()      { return noise_(rng_) * 0.4; }
double VitalsSimulator::temp_noise()    { return noise_(rng_) * 0.02; }
double VitalsSimulator::glucose_noise() { return noise_(rng_) * 2.0; }
double VitalsSimulator::lactate_noise() { return noise_(rng_) * 0.05; }

} // namespace icu
