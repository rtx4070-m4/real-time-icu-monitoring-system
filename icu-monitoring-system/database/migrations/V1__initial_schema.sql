-- ICU Monitoring System – PostgreSQL Schema
-- Migration: V1__initial_schema.sql

-- ── Extensions ────────────────────────────────────────────────────────────────
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";    -- For text search on patient names

-- ── Users (authentication) ────────────────────────────────────────────────────
CREATE TABLE users (
    id           BIGSERIAL    PRIMARY KEY,
    username     VARCHAR(50)  NOT NULL UNIQUE,
    email        VARCHAR(100) NOT NULL UNIQUE,
    password     VARCHAR(255) NOT NULL,
    full_name    VARCHAR(100) NOT NULL,
    role         VARCHAR(20)  NOT NULL DEFAULT 'NURSE'
                              CHECK (role IN ('ADMIN','PHYSICIAN','NURSE','VIEWER')),
    enabled      BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- Default admin user (password: 'admin123' – change in production!)
INSERT INTO users (username, email, password, full_name, role)
VALUES (
    'admin',
    'admin@icu-system.local',
    '$2a$12$RgK1wRDiX3EJz8SmQ5L4QuNJC1n1tPy6XWDE5n7bqOeSxXkHZJm3i',
    'System Administrator',
    'ADMIN'
);

INSERT INTO users (username, email, password, full_name, role)
VALUES (
    'dr.smith',
    'dr.smith@icu-system.local',
    '$2a$12$RgK1wRDiX3EJz8SmQ5L4QuNJC1n1tPy6XWDE5n7bqOeSxXkHZJm3i',
    'Dr. Sarah Smith',
    'PHYSICIAN'
);

INSERT INTO users (username, email, password, full_name, role)
VALUES (
    'nurse.jones',
    'nurse.jones@icu-system.local',
    '$2a$12$RgK1wRDiX3EJz8SmQ5L4QuNJC1n1tPy6XWDE5n7bqOeSxXkHZJm3i',
    'Nurse Michael Jones',
    'NURSE'
);

-- ── Vital records ─────────────────────────────────────────────────────────────
CREATE TABLE vital_records (
    id               BIGSERIAL    PRIMARY KEY,
    patient_id       VARCHAR(20)  NOT NULL,
    heart_rate       DOUBLE PRECISION NOT NULL,
    systolic_bp      DOUBLE PRECISION NOT NULL,
    diastolic_bp     DOUBLE PRECISION NOT NULL,
    spo2             DOUBLE PRECISION NOT NULL,
    respiratory_rate DOUBLE PRECISION NOT NULL,
    temperature      DOUBLE PRECISION NOT NULL,
    glucose          DOUBLE PRECISION NOT NULL DEFAULT 90,
    lactate          DOUBLE PRECISION NOT NULL DEFAULT 1.0,
    severity         VARCHAR(15)  NOT NULL DEFAULT 'STABLE'
                                  CHECK (severity IN ('STABLE','ELEVATED','CRITICAL','CODE_BLUE')),
    news2_score      INTEGER,
    ai_risk_score    DOUBLE PRECISION,
    ai_risk_category VARCHAR(20),
    timestamp        TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_vr_patient_id ON vital_records (patient_id);
CREATE INDEX idx_vr_timestamp  ON vital_records (timestamp DESC);
CREATE INDEX idx_vr_severity   ON vital_records (severity);
CREATE INDEX idx_vr_patient_ts ON vital_records (patient_id, timestamp DESC);

-- ── Patients ──────────────────────────────────────────────────────────────────
CREATE TABLE patients (
    id                  BIGSERIAL    PRIMARY KEY,
    patient_id          VARCHAR(20)  NOT NULL UNIQUE,
    name                VARCHAR(100) NOT NULL,
    age                 INTEGER      NOT NULL CHECK (age BETWEEN 0 AND 130),
    diagnosis           VARCHAR(100) NOT NULL,
    bed_number          INTEGER      NOT NULL UNIQUE,
    priority            INTEGER      NOT NULL DEFAULT 5 CHECK (priority BETWEEN 1 AND 5),
    active              BOOLEAN      NOT NULL DEFAULT TRUE,
    severity            VARCHAR(15)  NOT NULL DEFAULT 'STABLE'
                                     CHECK (severity IN ('STABLE','ELEVATED','CRITICAL','CODE_BLUE')),
    admission_time      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    notes               VARCHAR(500),
    attending_physician VARCHAR(100),
    latest_vitals_id    BIGINT       REFERENCES vital_records(id) ON DELETE SET NULL,
    created_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_patient_id  ON patients (patient_id);
CREATE INDEX idx_bed_number  ON patients (bed_number);
CREATE INDEX idx_active      ON patients (active);
CREATE INDEX idx_severity    ON patients (severity);
CREATE INDEX idx_name_trgm   ON patients USING GIN (name gin_trgm_ops);

-- Trigger: auto-update updated_at
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER patients_updated_at
    BEFORE UPDATE ON patients
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ── Alerts ────────────────────────────────────────────────────────────────────
CREATE TABLE alerts (
    id               BIGSERIAL    PRIMARY KEY,
    alert_id         VARCHAR(50)  NOT NULL UNIQUE,
    patient_id       VARCHAR(20)  NOT NULL,
    alert_type       VARCHAR(50)  NOT NULL,
    severity         VARCHAR(15)  NOT NULL
                                  CHECK (severity IN ('STABLE','ELEVATED','CRITICAL','CODE_BLUE')),
    message          VARCHAR(500) NOT NULL,

    -- Vitals snapshot at time of alert
    vitals_hr        DOUBLE PRECISION,
    vitals_sbp       DOUBLE PRECISION,
    vitals_dbp       DOUBLE PRECISION,
    vitals_spo2      DOUBLE PRECISION,
    vitals_rr        DOUBLE PRECISION,
    vitals_temp      DOUBLE PRECISION,
    vitals_lac       DOUBLE PRECISION,

    triggered_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    acknowledged     BOOLEAN      NOT NULL DEFAULT FALSE,
    acknowledged_at  TIMESTAMPTZ,
    acknowledged_by  VARCHAR(100),
    notes            VARCHAR(500),
    created_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_alert_patient_id   ON alerts (patient_id);
CREATE INDEX idx_alert_triggered_at ON alerts (triggered_at DESC);
CREATE INDEX idx_alert_severity     ON alerts (severity);
CREATE INDEX idx_alert_acknowledged ON alerts (acknowledged);
CREATE INDEX idx_alert_composite    ON alerts (patient_id, triggered_at DESC);

-- ── Audit log ─────────────────────────────────────────────────────────────────
CREATE TABLE audit_log (
    id          BIGSERIAL    PRIMARY KEY,
    username    VARCHAR(50),
    action      VARCHAR(100) NOT NULL,
    entity_type VARCHAR(50),
    entity_id   VARCHAR(50),
    details     TEXT,
    ip_address  VARCHAR(45),
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_audit_username   ON audit_log (username);
CREATE INDEX idx_audit_created_at ON audit_log (created_at DESC);

-- ── TimescaleDB hypertable (if extension available) ───────────────────────────
-- Converts vital_records into a time-series optimised hypertable (optional)
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'timescaledb') THEN
        PERFORM create_hypertable('vital_records', 'timestamp',
            chunk_time_interval => INTERVAL '1 day',
            if_not_exists => TRUE);
        RAISE NOTICE 'TimescaleDB hypertable created for vital_records';
    ELSE
        RAISE NOTICE 'TimescaleDB not available – using standard PostgreSQL table';
    END IF;
END $$;

-- ── Data retention policy ─────────────────────────────────────────────────────
-- Delete vitals older than 90 days (run via cron or pg_cron)
CREATE OR REPLACE FUNCTION purge_old_vitals()
RETURNS void AS $$
BEGIN
    DELETE FROM vital_records
    WHERE timestamp < NOW() - INTERVAL '90 days';
END;
$$ LANGUAGE plpgsql;

-- ── Sample data: 8 ICU patients ───────────────────────────────────────────────
INSERT INTO patients (patient_id, name, age, diagnosis, bed_number, priority, severity, attending_physician)
VALUES
    ('P001', 'Ahmad Khan',      72, 'SEPSIS',              1, 1, 'CRITICAL', 'Dr. Smith'),
    ('P002', 'Priya Sharma',    58, 'CARDIAC_FAILURE',     2, 2, 'CRITICAL', 'Dr. Smith'),
    ('P003', 'James Wilson',    45, 'TRAUMA',              3, 2, 'ELEVATED', 'Dr. Patel'),
    ('P004', 'Maria Garcia',    66, 'RESPIRATORY_FAILURE', 4, 1, 'CRITICAL', 'Dr. Smith'),
    ('P005', 'David Lee',       81, 'STROKE',              5, 3, 'ELEVATED', 'Dr. Patel'),
    ('P006', 'Fatima Al-Sayed', 34, 'TRAUMA',              6, 2, 'ELEVATED', 'Dr. Johnson'),
    ('P007', 'Robert Johnson',  55, 'SEPSIS',              7, 2, 'CRITICAL', 'Dr. Johnson'),
    ('P008', 'Sunita Patel',    70, 'CARDIAC_FAILURE',     8, 3, 'STABLE',   'Dr. Patel');

COMMENT ON TABLE patients     IS 'ICU patient registry';
COMMENT ON TABLE vital_records IS 'Time-series vital sign measurements';
COMMENT ON TABLE alerts        IS 'Clinical alert events from the Rust alert engine';
COMMENT ON TABLE users         IS 'System users (physicians, nurses, admins)';
COMMENT ON TABLE audit_log     IS 'Security and clinical audit trail';
