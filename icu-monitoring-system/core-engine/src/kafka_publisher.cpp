#include "kafka_publisher.hpp"
#include <iostream>
#include <chrono>
#include <iomanip>
#include <sstream>

// librdkafka C++ wrapper
// In production build, link with -lrdkafka++
// For mock/testing purposes when Kafka is not available, we log to stdout

namespace icu {

// Internal implementation - abstracts Kafka producer
struct KafkaPublisher::Impl {
    // In a real build: rd_kafka_t* producer; rd_kafka_topic_t* topic;
    // For portability in this build, we simulate via stdout
    bool kafka_available = false;
    std::string broker_list;

    Impl(const std::string& brokers) : broker_list(brokers) {
        // Attempt to detect if Kafka is reachable
        // Real implementation would call rd_kafka_new() here
        std::cout << "[Kafka] Publisher targeting brokers: " << brokers << "\n";
    }

    bool send(const std::string& topic, const std::string& key,
              const std::string& payload) {
        // Real implementation:
        //   rd_kafka_produce(rkt_, partition, RD_KAFKA_MSG_F_COPY,
        //                    payload.data(), payload.size(), key.data(), key.size(), NULL);
        std::cout << "[Kafka->'" << topic << "'] key=" << key
                  << " len=" << payload.size() << "B\n";
        return true;
    }
};

KafkaPublisher::KafkaPublisher(const std::string& brokers,
                               const std::string& vitals_topic,
                               const std::string& alerts_topic)
    : impl_(std::make_unique<Impl>(brokers)),
      brokers_(brokers),
      vitals_topic_(vitals_topic),
      alerts_topic_(alerts_topic) {}

KafkaPublisher::~KafkaPublisher() {
    flush();
}

bool KafkaPublisher::publish_vitals(const std::string& patient_id,
                                     const VitalSigns& vitals) {
    auto payload = vitals_to_json(patient_id, vitals);
    return impl_->send(vitals_topic_, patient_id, payload.dump());
}

bool KafkaPublisher::publish_alert(const std::string& patient_id,
                                    const std::string& alert_type,
                                    const std::string& message,
                                    Severity severity) {
    nlohmann::json j;
    j["patient_id"]  = patient_id;
    j["alert_type"]  = alert_type;
    j["message"]     = message;
    j["severity"]    = static_cast<int>(severity);

    // ISO-8601 timestamp
    auto now = std::chrono::system_clock::now();
    auto t   = std::chrono::system_clock::to_time_t(now);
    std::ostringstream ts;
    ts << std::put_time(std::gmtime(&t), "%Y-%m-%dT%H:%M:%SZ");
    j["timestamp"] = ts.str();

    return impl_->send(alerts_topic_, patient_id, j.dump());
}

void KafkaPublisher::flush(int /*timeout_ms*/) {
    // Real: rd_kafka_flush(producer_, timeout_ms);
    std::cout << "[Kafka] Flush complete\n";
}

nlohmann::json KafkaPublisher::vitals_to_json(const std::string& patient_id,
                                               const VitalSigns& v) {
    nlohmann::json j;
    j["patient_id"]        = patient_id;
    j["heart_rate"]        = v.heart_rate;
    j["systolic_bp"]       = v.systolic_bp;
    j["diastolic_bp"]      = v.diastolic_bp;
    j["spo2"]              = v.spo2;
    j["respiratory_rate"]  = v.respiratory_rate;
    j["temperature"]       = v.temperature;
    j["glucose"]           = v.glucose;
    j["lactate"]           = v.lactate;
    j["severity"]          = static_cast<int>(v.severity);

    // ISO-8601 timestamp
    auto t = std::chrono::system_clock::to_time_t(v.timestamp);
    std::ostringstream ts;
    ts << std::put_time(std::gmtime(&t), "%Y-%m-%dT%H:%M:%SZ");
    j["timestamp"] = ts.str();

    return j;
}

} // namespace icu
