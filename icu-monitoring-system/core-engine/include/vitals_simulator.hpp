#pragma once
#include "patient.hpp"
#include <random>
#include <chrono>

namespace icu {

// Simulates realistic ICU patient vitals with physiological trends
class VitalsSimulator {
public:
    VitalsSimulator();

    // Generate initial vitals for a new patient
    VitalSigns generate_initial_vitals(int age, const std::string& diagnosis);

    // Update vitals: applies trends + random noise + physiological coupling
    VitalSigns update_vitals(const VitalSigns& current,
                             double hr_trend,
                             double bp_trend,
                             double spo2_trend,
                             double rr_trend,
                             double temp_trend);

    // Compute severity from vitals (NEWS2-style scoring)
    Severity compute_severity(const VitalSigns& v);

    // Compute a NEWS2-compatible early warning score
    int compute_news2_score(const VitalSigns& v);

    // Introduce a deterioration episode
    void apply_deterioration_event(PatientState& patient);

    // Clamp vitals to physiologically plausible ranges
    VitalSigns clamp_vitals(const VitalSigns& v) const;

private:
    std::mt19937 rng_;
    std::normal_distribution<double> noise_;

    // Per-vital noise generators
    double hr_noise();
    double bp_noise();
    double spo2_noise();
    double rr_noise();
    double temp_noise();
    double glucose_noise();
    double lactate_noise();
};

} // namespace icu
