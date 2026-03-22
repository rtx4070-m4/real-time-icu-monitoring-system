#include "scheduler.hpp"
#include "vitals_simulator.hpp"
#include <iostream>
#include <chrono>
#include <algorithm>

namespace icu {

ICUScheduler::ICUScheduler(int worker_threads)
    : num_workers_(worker_threads) {}

ICUScheduler::~ICUScheduler() {
    stop();
}

void ICUScheduler::add_patient(std::shared_ptr<PatientState> patient) {
    {
        std::lock_guard<std::mutex> lk(patients_mutex_);
        patients_[patient->patient_id] = patient;
    }
    std::cout << "[Scheduler] Added patient: " << patient->patient_id
              << " (" << patient->name << "), priority=" << patient->priority << "\n";

    // Enqueue immediately for first vitals generation
    dispatch_patient(patient);
}

void ICUScheduler::remove_patient(const std::string& patient_id) {
    std::lock_guard<std::mutex> lk(patients_mutex_);
    auto it = patients_.find(patient_id);
    if (it != patients_.end()) {
        it->second->active.store(false);
        patients_.erase(it);
        std::cout << "[Scheduler] Removed patient: " << patient_id << "\n";
    }
}

void ICUScheduler::update_priority(const std::string& patient_id, int new_priority) {
    std::lock_guard<std::mutex> lk(patients_mutex_);
    auto it = patients_.find(patient_id);
    if (it != patients_.end()) {
        it->second->priority = new_priority;
        std::cout << "[Scheduler] Updated priority for " << patient_id
                  << " to " << new_priority << "\n";
    }
}

void ICUScheduler::set_vitals_callback(VitalsCallback cb) {
    std::lock_guard<std::mutex> lk(callback_mutex_);
    vitals_callback_ = std::move(cb);
}

void ICUScheduler::start() {
    running_.store(true);

    // Start worker thread pool
    for (int i = 0; i < num_workers_; ++i) {
        workers_.emplace_back(&ICUScheduler::worker_loop, this, i);
    }

    // Start scheduler (re-queues patients continuously)
    scheduler_thread_ = std::thread(&ICUScheduler::scheduler_loop, this);

    std::cout << "[Scheduler] Started with " << num_workers_ << " workers\n";
}

void ICUScheduler::stop() {
    if (!running_.load()) return;

    running_.store(false);
    queue_cv_.notify_all();

    for (auto& w : workers_) {
        if (w.joinable()) w.join();
    }
    if (scheduler_thread_.joinable()) {
        scheduler_thread_.join();
    }

    workers_.clear();
    std::cout << "[Scheduler] Stopped\n";
}

size_t ICUScheduler::patient_count() const {
    std::lock_guard<std::mutex> lk(patients_mutex_);
    return patients_.size();
}

std::shared_ptr<PatientState> ICUScheduler::get_patient(const std::string& id) const {
    std::lock_guard<std::mutex> lk(patients_mutex_);
    auto it = patients_.find(id);
    return (it != patients_.end()) ? it->second : nullptr;
}

// Dispatch a patient to the priority work queue
void ICUScheduler::dispatch_patient(std::shared_ptr<PatientState> patient) {
    {
        std::lock_guard<std::mutex> lk(queue_mutex_);
        work_queue_.push(patient);
    }
    queue_cv_.notify_one();
}

// Worker thread: processes vitals updates for patients
void ICUScheduler::worker_loop(int thread_id) {
    VitalsSimulator sim;
    std::cout << "[Worker-" << thread_id << "] Started\n";

    while (running_.load()) {
        std::shared_ptr<PatientState> patient;

        {
            std::unique_lock<std::mutex> lk(queue_mutex_);
            queue_cv_.wait(lk, [&] {
                return !work_queue_.empty() || !running_.load();
            });

            if (!running_.load()) break;
            if (work_queue_.empty()) continue;

            patient = work_queue_.top();
            work_queue_.pop();
        }

        if (!patient || !patient->active.load()) continue;

        // Simulate vitals update
        VitalSigns new_vitals;
        {
            std::lock_guard<std::mutex> vlk(patient->vitals_mutex);
            new_vitals = sim.update_vitals(
                patient->current_vitals,
                patient->hr_trend,
                patient->bp_trend,
                patient->spo2_trend,
                patient->rr_trend,
                patient->temp_trend
            );
            patient->current_vitals = new_vitals;

            // Randomly trigger deterioration events (~1% chance per update)
            std::mt19937 rng(std::random_device{}());
            std::uniform_real_distribution<double> dist(0.0, 1.0);
            if (dist(rng) < 0.01 && !patient->deteriorating.load()) {
                sim.apply_deterioration_event(*patient);
            }

            // Gradually recover from deterioration
            if (patient->deteriorating.load()) {
                patient->hr_trend   *= 0.95;
                patient->bp_trend   *= 0.95;
                patient->spo2_trend *= 0.95;
                if (std::abs(patient->hr_trend) < 0.05) {
                    patient->hr_trend   = 0.0;
                    patient->bp_trend   = 0.0;
                    patient->spo2_trend = 0.0;
                    patient->deteriorating.store(false);
                }
            }

            // Update patient priority based on severity
            switch (new_vitals.severity) {
                case Severity::CODE_BLUE: patient->priority = 1; break;
                case Severity::CRITICAL:  patient->priority = 2; break;
                case Severity::ELEVATED:  patient->priority = 3; break;
                case Severity::STABLE:    patient->priority = 5; break;
            }
        }

        // Fire the vitals callback
        {
            std::lock_guard<std::mutex> clk(callback_mutex_);
            if (vitals_callback_) {
                vitals_callback_(patient->patient_id, new_vitals);
            }
        }
    }

    std::cout << "[Worker-" << thread_id << "] Stopped\n";
}

// Scheduler loop: continuously re-queues active patients at their update rate
void ICUScheduler::scheduler_loop() {
    using namespace std::chrono_literals;
    std::cout << "[Scheduler-Loop] Started\n";

    while (running_.load()) {
        // Collect active patients
        std::vector<std::shared_ptr<PatientState>> active_patients;
        {
            std::lock_guard<std::mutex> lk(patients_mutex_);
            for (auto& [id, p] : patients_) {
                if (p->active.load()) {
                    active_patients.push_back(p);
                }
            }
        }

        // Enqueue each patient; critical patients get more frequent updates
        for (auto& p : active_patients) {
            if (!p->active.load()) continue;

            // Update interval: priority 1 = 500ms, priority 5 = 2000ms
            auto interval_ms = std::chrono::milliseconds(500 + (p->priority - 1) * 375);

            // Check when this patient was last processed
            auto now = std::chrono::system_clock::now();
            auto elapsed = std::chrono::duration_cast<std::chrono::milliseconds>(
                now - p->current_vitals.timestamp
            );

            if (elapsed >= interval_ms) {
                dispatch_patient(p);
            }
        }

        // Scheduler ticks every 200ms
        std::this_thread::sleep_for(200ms);
    }

    std::cout << "[Scheduler-Loop] Stopped\n";
}

} // namespace icu
