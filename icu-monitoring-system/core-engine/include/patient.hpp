#pragma once
#include <string>
#include <atomic>
#include <mutex>
#include <chrono>
#include <functional>

namespace icu {

// ICU severity levels
enum class Severity { STABLE, ELEVATED, CRITICAL, CODE_BLUE };

// Vital signs snapshot
struct VitalSigns {
    double heart_rate;        // bpm
    double systolic_bp;       // mmHg
    double diastolic_bp;      // mmHg
    double spo2;              // % oxygen saturation
    double respiratory_rate;  // breaths/min
    double temperature;       // Celsius
    double glucose;           // mg/dL
    double lactate;           // mmol/L
    Severity severity;
    std::chrono::system_clock::time_point timestamp;
};

// Patient state structure
struct PatientState {
    std::string patient_id;
    std::string name;
    int age;
    std::string diagnosis;
    int bed_number;
    int priority;             // 1=critical, 5=stable (for scheduler)
    std::atomic<bool> active{true};
    std::atomic<bool> deteriorating{false};
    VitalSigns current_vitals;
    mutable std::mutex vitals_mutex;

    // Trend modifiers (simulate patient condition changes)
    double hr_trend    = 0.0;
    double bp_trend    = 0.0;
    double spo2_trend  = 0.0;
    double rr_trend    = 0.0;
    double temp_trend  = 0.0;
};

// Callback when vitals are updated
using VitalsCallback = std::function<void(const std::string&, const VitalSigns&)>;

} // namespace icu
