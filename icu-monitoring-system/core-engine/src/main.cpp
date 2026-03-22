#include "scheduler.hpp"
#include "vitals_simulator.hpp"
#include "kafka_publisher.hpp"
#include <iostream>
#include <memory>
#include <vector>
#include <csignal>
#include <atomic>
#include <chrono>
#include <thread>
#include <cstdlib>

// ─── Global shutdown flag ─────────────────────────────────────────────────────
static std::atomic<bool> g_shutdown{false};

void signal_handler(int sig) {
    std::cout << "\n[Main] Received signal " << sig << ", shutting down...\n";
    g_shutdown.store(true);
}

// ─── Helper: create a test patient ───────────────────────────────────────────
std::shared_ptr<icu::PatientState> make_patient(
    const std::string& id,
    const std::string& name,
    int age,
    const std::string& diagnosis,
    int bed,
    int priority)
{
    auto p = std::make_shared<icu::PatientState>();
    p->patient_id = id;
    p->name       = name;
    p->age        = age;
    p->diagnosis  = diagnosis;
    p->bed_number = bed;
    p->priority   = priority;

    // Generate initial vitals
    icu::VitalsSimulator sim;
    p->current_vitals = sim.generate_initial_vitals(age, diagnosis);

    return p;
}

int main(int argc, char* argv[]) {
    std::signal(SIGINT,  signal_handler);
    std::signal(SIGTERM, signal_handler);

    // Configuration from environment (Docker-friendly)
    const char* kafka_brokers_env = std::getenv("KAFKA_BROKERS");
    std::string kafka_brokers = kafka_brokers_env
        ? kafka_brokers_env
        : "kafka:9092";

    std::cout << "╔══════════════════════════════════════════════════════╗\n"
              << "║   ICU Real-Time Monitoring System - Core Engine      ║\n"
              << "║   Language: C++17  |  Pattern: Priority Scheduler    ║\n"
              << "╚══════════════════════════════════════════════════════╝\n\n";

    // ── 1. Kafka publisher ───────────────────────────────────────────────────
    auto kafka = std::make_shared<icu::KafkaPublisher>(kafka_brokers);

    // ── 2. Scheduler (4 worker threads = 4 patients processed concurrently) ─
    icu::ICUScheduler scheduler(4);

    // ── 3. Register vitals callback ──────────────────────────────────────────
    scheduler.set_vitals_callback([&kafka](const std::string& patient_id,
                                           const icu::VitalSigns& vitals) {
        // Publish to Kafka
        kafka->publish_vitals(patient_id, vitals);

        // Log critical events
        if (vitals.severity == icu::Severity::CODE_BLUE) {
            std::cout << "🚨 CODE BLUE: Patient " << patient_id
                      << " | HR=" << vitals.heart_rate
                      << " SpO2=" << vitals.spo2
                      << " BP=" << vitals.systolic_bp << "/" << vitals.diastolic_bp
                      << "\n";
            kafka->publish_alert(patient_id, "CODE_BLUE",
                "Immediate intervention required", icu::Severity::CODE_BLUE);
        } else if (vitals.severity == icu::Severity::CRITICAL) {
            std::cout << "⚠️  CRITICAL: Patient " << patient_id
                      << " | SpO2=" << vitals.spo2
                      << " Lactate=" << vitals.lactate << "\n";
        }
    });

    // ── 4. Add test patients ─────────────────────────────────────────────────
    std::vector<std::shared_ptr<icu::PatientState>> patients = {
        make_patient("P001", "Ahmad Khan",     72, "SEPSIS",              1, 1),
        make_patient("P002", "Priya Sharma",   58, "CARDIAC_FAILURE",     2, 2),
        make_patient("P003", "James Wilson",   45, "TRAUMA",              3, 2),
        make_patient("P004", "Maria Garcia",   66, "RESPIRATORY_FAILURE", 4, 1),
        make_patient("P005", "David Lee",      81, "STROKE",              5, 3),
        make_patient("P006", "Fatima Al-Sayed",34, "TRAUMA",              6, 2),
        make_patient("P007", "Robert Johnson", 55, "SEPSIS",              7, 2),
        make_patient("P008", "Sunita Patel",   70, "CARDIAC_FAILURE",     8, 3),
    };

    // ── 5. Start scheduler ───────────────────────────────────────────────────
    scheduler.start();

    for (auto& p : patients) {
        scheduler.add_patient(p);
        std::this_thread::sleep_for(std::chrono::milliseconds(50));
    }

    std::cout << "\n[Main] Monitoring " << scheduler.patient_count()
              << " patients. Press Ctrl-C to stop.\n\n";

    // ── 6. Main loop: print summary every 5 seconds ──────────────────────────
    using namespace std::chrono_literals;

    while (!g_shutdown.load()) {
        std::this_thread::sleep_for(5s);

        if (g_shutdown.load()) break;

        std::cout << "\n── Vitals Summary (" << scheduler.patient_count()
                  << " patients) ──────────────────────────────\n";
        std::cout << std::left
                  << std::setw(8)  << "ID"
                  << std::setw(20) << "Name"
                  << std::setw(8)  << "HR"
                  << std::setw(10) << "BP"
                  << std::setw(8)  << "SpO2"
                  << std::setw(6)  << "RR"
                  << std::setw(8)  << "Temp"
                  << std::setw(10) << "Status"
                  << "\n";
        std::cout << std::string(78, '-') << "\n";

        for (auto& p : patients) {
            if (!p->active.load()) continue;
            std::lock_guard<std::mutex> lk(p->vitals_mutex);
            const auto& v = p->current_vitals;

            const char* status_str = "STABLE";
            switch (v.severity) {
                case icu::Severity::ELEVATED:  status_str = "ELEVATED"; break;
                case icu::Severity::CRITICAL:  status_str = "CRITICAL"; break;
                case icu::Severity::CODE_BLUE: status_str = "CODE BLUE"; break;
                default: break;
            }

            std::cout << std::left
                      << std::setw(8)  << p->patient_id
                      << std::setw(20) << p->name
                      << std::setw(8)  << std::fixed << std::setprecision(0) << v.heart_rate
                      << std::setw(10) << (std::to_string((int)v.systolic_bp) + "/" +
                                           std::to_string((int)v.diastolic_bp))
                      << std::setw(8)  << std::setprecision(1) << v.spo2
                      << std::setw(6)  << std::setprecision(0) << v.respiratory_rate
                      << std::setw(8)  << std::setprecision(1) << v.temperature
                      << std::setw(10) << status_str
                      << "\n";
        }
    }

    // ── 7. Graceful shutdown ─────────────────────────────────────────────────
    std::cout << "\n[Main] Stopping scheduler...\n";
    scheduler.stop();
    kafka->flush();
    std::cout << "[Main] Core engine stopped cleanly.\n";

    return 0;
}
