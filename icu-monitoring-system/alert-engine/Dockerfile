FROM rust:1.75-slim AS builder

# Install system dependencies for rdkafka (cmake build)
RUN apt-get update && apt-get install -y \
    cmake \
    libssl-dev \
    pkg-config \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# Cache dependencies layer
COPY Cargo.toml Cargo.lock* ./
RUN mkdir src && echo "fn main() {}" > src/main.rs
RUN cargo build --release 2>/dev/null || true
RUN rm src/main.rs

# Build actual source
COPY src ./src
RUN cargo build --release

# ── Runtime ───────────────────────────────────────────────────────────────────
FROM debian:bookworm-slim

RUN apt-get update && apt-get install -y \
    libssl3 \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=builder /build/target/release/alert-engine .

ENV RUST_LOG=info
ENV KAFKA_BROKERS=kafka:9092
ENV KAFKA_VITALS_TOPIC=icu.vitals
ENV KAFKA_ALERTS_TOPIC=icu.alerts
ENV KAFKA_GROUP_ID=icu-alert-engine
ENV BACKEND_URL=http://backend-api:8080

CMD ["./alert-engine"]
