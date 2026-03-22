// src/components/dashboard/PatientCard.tsx
import React, { useState } from 'react';
import {
  Patient, VitalRecord, Severity, SEVERITY_COLORS, SEVERITY_BG, VITAL_NORMAL_RANGES
} from '../../types';

interface Props {
  patient:    Patient;
  latestVitals?: VitalRecord;
  onClick:    (patient: Patient) => void;
  isSelected: boolean;
}

const severityLabel: Record<Severity, string> = {
  STABLE:    'STABLE',
  ELEVATED:  'ELEVATED',
  CRITICAL:  'CRITICAL',
  CODE_BLUE: '⚡ CODE BLUE',
};

const VitalBadge: React.FC<{
  label: string;
  value: number | string;
  unit: string;
  min?: number;
  max?: number;
  invert?: boolean;   // lower = worse (SpO2, BP)
}> = ({ label, value, unit, min, max, invert = false }) => {
  const num = typeof value === 'string' ? parseFloat(value) : value;
  let color = '#6b7280';
  if (min !== undefined && max !== undefined && !isNaN(num)) {
    const ok = num >= min && num <= max;
    const critical = invert ? num < min * 0.9 : num > max * 1.2;
    color = ok ? '#22c55e' : critical ? '#ef4444' : '#f59e0b';
  }
  return (
    <div style={{ textAlign: 'center', padding: '4px 6px' }}>
      <div style={{ fontSize: 11, color: '#9ca3af', marginBottom: 2 }}>{label}</div>
      <div style={{ fontSize: 15, fontWeight: 600, color, fontFamily: 'monospace' }}>
        {typeof value === 'number' ? value.toFixed(label === 'TEMP' || label === 'SpO2' ? 1 : 0) : value}
      </div>
      <div style={{ fontSize: 10, color: '#6b7280' }}>{unit}</div>
    </div>
  );
};

export const PatientCard: React.FC<Props> = ({ patient, latestVitals, onClick, isSelected }) => {
  const v    = latestVitals ?? patient.latestVitals;
  const sev  = patient.severity;
  const color = SEVERITY_COLORS[sev];
  const bg    = SEVERITY_BG[sev];
  const isCodeBlue = sev === 'CODE_BLUE';

  return (
    <div
      onClick={() => onClick(patient)}
      style={{
        background:    isSelected ? 'rgba(59,130,246,0.1)' : 'rgba(17,24,39,0.8)',
        border:        `2px solid ${isSelected ? '#3b82f6' : color}`,
        borderRadius:  12,
        padding:       16,
        cursor:        'pointer',
        position:      'relative',
        overflow:      'hidden',
        transition:    'all 0.2s ease',
        boxShadow:     isCodeBlue ? `0 0 20px ${color}44` : 'none',
        animation:     isCodeBlue ? 'codeBluePulse 1.5s ease-in-out infinite' : 'none',
      }}
    >
      {/* Severity stripe */}
      <div style={{
        position: 'absolute', top: 0, left: 0, right: 0, height: 3,
        background: color,
      }} />

      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 10 }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{
              background: 'rgba(59,130,246,0.2)', color: '#60a5fa',
              borderRadius: 6, padding: '2px 8px', fontSize: 12, fontWeight: 600,
            }}>
              BED {patient.bedNumber}
            </span>
            <span style={{ fontSize: 12, color: '#6b7280' }}>{patient.patientId}</span>
          </div>
          <div style={{ fontSize: 16, fontWeight: 700, color: '#f9fafb', marginTop: 4 }}>
            {patient.name}
          </div>
          <div style={{ fontSize: 12, color: '#9ca3af' }}>
            {patient.age}y · {patient.diagnosis.replace(/_/g, ' ')}
          </div>
        </div>

        <div style={{
          background: bg, border: `1px solid ${color}`,
          borderRadius: 8, padding: '4px 10px', textAlign: 'center',
        }}>
          <div style={{ fontSize: 10, color: '#9ca3af' }}>STATUS</div>
          <div style={{ fontSize: 12, fontWeight: 700, color, letterSpacing: 0.5 }}>
            {severityLabel[sev]}
          </div>
        </div>
      </div>

      {/* Vitals grid */}
      {v ? (
        <div style={{
          display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)',
          gap: 2, background: 'rgba(255,255,255,0.04)',
          borderRadius: 8, padding: 8, marginBottom: 8,
        }}>
          <VitalBadge
            label="HR"
            value={v.heartRate}
            unit="bpm"
            min={VITAL_NORMAL_RANGES.heartRate.min}
            max={VITAL_NORMAL_RANGES.heartRate.max}
          />
          <VitalBadge
            label="BP"
            value={`${v.systolicBp.toFixed(0)}/${v.diastolicBp.toFixed(0)}`}
            unit="mmHg"
          />
          <VitalBadge
            label="SpO2"
            value={v.spo2}
            unit="%"
            min={VITAL_NORMAL_RANGES.spo2.min}
            max={VITAL_NORMAL_RANGES.spo2.max}
            invert
          />
          <VitalBadge
            label="RR"
            value={v.respiratoryRate}
            unit="br/min"
            min={VITAL_NORMAL_RANGES.respiratoryRate.min}
            max={VITAL_NORMAL_RANGES.respiratoryRate.max}
          />
          <VitalBadge
            label="TEMP"
            value={v.temperature}
            unit="°C"
            min={VITAL_NORMAL_RANGES.temperature.min}
            max={VITAL_NORMAL_RANGES.temperature.max}
          />
          <VitalBadge
            label="GLUCOSE"
            value={v.glucose}
            unit="mg/dL"
            min={VITAL_NORMAL_RANGES.glucose.min}
            max={VITAL_NORMAL_RANGES.glucose.max}
          />
          <VitalBadge
            label="LACTATE"
            value={v.lactate}
            unit="mmol/L"
            min={VITAL_NORMAL_RANGES.lactate.min}
            max={VITAL_NORMAL_RANGES.lactate.max}
          />
          {v.news2Score !== undefined && (
            <VitalBadge
              label="NEWS2"
              value={v.news2Score}
              unit="score"
              min={0}
              max={4}
            />
          )}
        </div>
      ) : (
        <div style={{
          textAlign: 'center', padding: 16, color: '#4b5563', fontSize: 13,
          background: 'rgba(255,255,255,0.03)', borderRadius: 8, marginBottom: 8,
        }}>
          Awaiting vitals...
        </div>
      )}

      {/* AI Risk */}
      {v?.aiRiskScore !== undefined && (
        <div style={{
          display: 'flex', alignItems: 'center', gap: 8,
          padding: '6px 10px', background: 'rgba(0,0,0,0.3)', borderRadius: 6,
        }}>
          <span style={{ fontSize: 11, color: '#9ca3af' }}>AI Risk</span>
          <div style={{
            flex: 1, height: 4, background: '#1f2937', borderRadius: 2, overflow: 'hidden',
          }}>
            <div style={{
              height: '100%', borderRadius: 2,
              width: `${(v.aiRiskScore ?? 0) * 100}%`,
              background: v.aiRiskScore! > 0.6 ? '#ef4444' : v.aiRiskScore! > 0.35 ? '#f59e0b' : '#22c55e',
              transition: 'width 1s ease',
            }} />
          </div>
          <span style={{
            fontSize: 12, fontWeight: 700,
            color: v.aiRiskScore! > 0.6 ? '#ef4444' : v.aiRiskScore! > 0.35 ? '#f59e0b' : '#22c55e',
          }}>
            {((v.aiRiskScore ?? 0) * 100).toFixed(0)}%
          </span>
        </div>
      )}

      {/* Footer */}
      <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 8, alignItems: 'center' }}>
        <span style={{ fontSize: 11, color: '#4b5563' }}>
          👨‍⚕️ {patient.attendingPhysician ?? 'Unassigned'}
        </span>
        <span style={{ fontSize: 10, color: '#374151' }}>
          {v ? new Date(v.timestamp).toLocaleTimeString() : '—'}
        </span>
      </div>
    </div>
  );
};
