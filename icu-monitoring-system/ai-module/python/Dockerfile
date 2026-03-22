FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY . .

ENV KAFKA_BROKERS=kafka:9092
ENV KAFKA_VITALS_TOPIC=icu.vitals
ENV AI_API_PORT=8082

EXPOSE 8082

CMD ["python", "api_server.py"]
