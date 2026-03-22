#pragma once
#include "patient.hpp"
#include <string>
#include <memory>
#include <nlohmann/json.hpp>

namespace icu {

// Publishes vitals events to Kafka using librdkafka
class KafkaPublisher {
public:
    explicit KafkaPublisher(const std::string& brokers,
                            const std::string& vitals_topic = "icu.vitals",
                            const std::string& alerts_topic = "icu.alerts");
    ~KafkaPublisher();

    // Publish a vitals update message
    bool publish_vitals(const std::string& patient_id,
                        const VitalSigns& vitals);

    // Publish a raw alert message (critical event shortcut)
    bool publish_alert(const std::string& patient_id,
                       const std::string& alert_type,
                       const std::string& message,
                       Severity severity);

    // Flush pending messages
    void flush(int timeout_ms = 5000);

private:
    // Convert VitalSigns to JSON payload
    nlohmann::json vitals_to_json(const std::string& patient_id,
                                  const VitalSigns& vitals);

    struct Impl;
    std::unique_ptr<Impl> impl_;

    std::string brokers_;
    std::string vitals_topic_;
    std::string alerts_topic_;
};

} // namespace icu
