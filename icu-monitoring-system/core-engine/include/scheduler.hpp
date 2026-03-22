#pragma once
#include "patient.hpp"
#include <vector>
#include <queue>
#include <memory>
#include <thread>
#include <condition_variable>
#include <unordered_map>

namespace icu {

// Priority comparator for the scheduler queue
struct PatientPriorityComparator {
    bool operator()(const std::shared_ptr<PatientState>& a,
                    const std::shared_ptr<PatientState>& b) const {
        // Lower priority number = higher urgency
        return a->priority > b->priority;
    }
};

// Priority queue type alias
using PatientQueue = std::priority_queue<
    std::shared_ptr<PatientState>,
    std::vector<std::shared_ptr<PatientState>>,
    PatientPriorityComparator
>;

class ICUScheduler {
public:
    explicit ICUScheduler(int worker_threads = 4);
    ~ICUScheduler();

    // Add a patient to the monitoring system
    void add_patient(std::shared_ptr<PatientState> patient);

    // Remove patient (discharge/transfer)
    void remove_patient(const std::string& patient_id);

    // Update patient priority based on vitals deterioration
    void update_priority(const std::string& patient_id, int new_priority);

    // Register a callback to receive vitals updates
    void set_vitals_callback(VitalsCallback cb);

    // Start/stop the scheduler
    void start();
    void stop();

    // Get number of active patients
    size_t patient_count() const;

    // Get current patient state by ID
    std::shared_ptr<PatientState> get_patient(const std::string& id) const;

private:
    void worker_loop(int thread_id);
    void scheduler_loop();
    void dispatch_patient(std::shared_ptr<PatientState> patient);

    int num_workers_;
    std::atomic<bool> running_{false};

    // Worker thread pool
    std::vector<std::thread> workers_;
    std::thread scheduler_thread_;

    // Patient registry
    mutable std::mutex patients_mutex_;
    std::unordered_map<std::string, std::shared_ptr<PatientState>> patients_;

    // Work queue (priority-ordered)
    mutable std::mutex queue_mutex_;
    std::condition_variable queue_cv_;
    PatientQueue work_queue_;

    // Vitals update callback
    VitalsCallback vitals_callback_;
    mutable std::mutex callback_mutex_;
};

} // namespace icu
