FROM maven:3.9-eclipse-temurin-21 AS builder

WORKDIR /build
COPY pom.xml .
RUN mvn dependency:go-offline -q

COPY src ./src
RUN mvn clean package -DskipTests -q

# ── Runtime ───────────────────────────────────────────────────────────────────
FROM eclipse-temurin:21-jre-jammy

WORKDIR /app

COPY --from=builder /build/target/icu-backend-api-1.0.0.jar app.jar

ENV DB_HOST=postgres
ENV DB_PORT=5432
ENV DB_NAME=icu_db
ENV DB_USER=icu_user
ENV DB_PASS=icu_pass
ENV KAFKA_BROKERS=kafka:9092
ENV SERVER_PORT=8080

EXPOSE 8080

ENTRYPOINT ["java", \
  "-Xms256m", "-Xmx512m", \
  "-XX:+UseG1GC", \
  "-Djava.security.egd=file:/dev/./urandom", \
  "-jar", "app.jar"]
