// src/components/alerts/AlertsPanel.tsx
import React, { useState } from 'react';
import { Alert, Severity, SEVERITY_COLORS, SEVERITY_BG } from '../../types';
import { api } from '../../services/api';

interface Props {
  alerts:       Alert[];
  currentUser:  string;
  onAcknowledge:(alertId: string) => void;
}

const alertTypeIcon: Record<string, string> = {
  TACHYCARDIA:         '💓',
  BRADYCARDIA:         '💔',
  HYPERTENSIVE_CRISIS: '🩸',
  HYPOTENSIVE_SHOCK:   '📉',
  HYPOXIA:             '🫁',
  APNEA:               '🚫',
  RESPIRATORY_DISTRESS:'😮‍💨',
  HYPERTHERMIA:        '🌡️',
  HYPOTHERMIA:         '❄️',
  LACTIC_ACIDOSIS:     '⚗️',
  SEPSIS_ALERT:        '🦠',
  CODE_BLUE:           '🚨',
  RAPID_DETERIORATION: '📊',
  HYPERGLYCEMIA:       '🍬',
  HYPOGLYCEMIA:        '⚡',
};

const AlertRow: React.FC<{
  alert:        Alert;
  currentUser:  string;
  onAck:        (alertId: string) => void;
}> = ({ alert, currentUser, onAck }) => {
  const [acking,  setAcking]  = useState(false);
  const [showNotes, setShowNotes] = useState(false);
  const [notes, setNotes]     = useState('');

  const color = SEVERITY_COLORS[alert.severity];
  const bg    = SEVERITY_BG[alert.severity];
  const icon  = alertTypeIcon[alert.alertType] ?? '⚠️';
  const ts    = new Date(alert.triggeredAt);
  const ago   = Math.round((Date.now() - ts.getTime()) / 60000);

  const handleAck = async () => {
    setAcking(true);
    try {
      await api.acknowledgeAlert(alert.alertId, currentUser, notes);
      onAck(alert.alertId);
    } finally {
      setAcking(false);
      setShowNotes(false);
    }
  };

  return (
    <div style={{
      background:    bg,
      border:        `1px solid ${color}44`,
      borderLeft:    `4px solid ${color}`,
      borderRadius:  8,
      padding:       12,
      marginBottom:  8,
      opacity:       alert.acknowledged ? 0.5 : 1,
      transition:    'opacity 0.3s',
    }}>
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10 }}>
        <span style={{ fontSize: 18 }}>{icon}</span>

        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
              <span style={{
                background: color + '22', color, border: `1px solid ${color}44`,
                borderRadius: 4, padding: '1px 6px', fontSize: 10, fontWeight: 700,
              }}>
                {alert.severity}
              </span>
              <span style={{ fontSize: 12, color: '#9ca3af', fontFamily: 'monospace' }}>
                {alert.patientId}
              </span>
            </div>
            <span style={{ fontSize: 11, color: '#4b5563' }}>
              {ago < 1 ? 'Just now' : `${ago}m ago`}
            </span>
          </div>

          <div style={{ fontSize: 13, color: '#e5e7eb', margin: '4px 0' }}>
            {alert.message}
          </div>

          {/* Vitals snapshot */}
          {(alert.vitalsSpo2 || alert.vitalsHr) && (
            <div style={{ display: 'flex', gap: 10, fontSize: 11, color: '#6b7280' }}>
              {alert.vitalsHr   && <span>HR {alert.vitalsHr.toFixed(0)}</span>}
              {alert.vitalsSpo2 && <span>SpO2 {alert.vitalsSpo2.toFixed(1)}%</span>}
              {alert.vitalsSbp  && <span>BP {alert.vitalsSbp.toFixed(0)}/{alert.vitalsDbp?.toFixed(0)}</span>}
              {alert.vitalsTemp && <span>{alert.vitalsTemp.toFixed(1)}°C</span>}
            </div>
          )}
        </div>

        {/* Acknowledge button */}
        {!alert.acknowledged && (
          <div>
            {!showNotes ? (
              <button
                onClick={() => setShowNotes(true)}
                style={{
                  background: 'rgba(59,130,246,0.15)', border: '1px solid #3b82f6',
                  color: '#60a5fa', borderRadius: 6, padding: '4px 10px',
                  fontSize: 11, cursor: 'pointer', whiteSpace: 'nowrap',
                }}
              >
                ACK
              </button>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                <textarea
                  value={notes}
                  onChange={e => setNotes(e.target.value)}
                  placeholder="Notes (optional)"
                  rows={2}
                  style={{
                    background: '#111827', border: '1px solid #374151',
                    color: '#f9fafb', borderRadius: 4, padding: 4,
                    fontSize: 11, resize: 'none', width: 160,
                  }}
                />
                <div style={{ display: 'flex', gap: 4 }}>
                  <button
                    onClick={handleAck}
                    disabled={acking}
                    style={{
                      background: '#3b82f6', border: 'none',
                      color: '#fff', borderRadius: 4, padding: '3px 8px',
                      fontSize: 11, cursor: 'pointer', flex: 1,
                    }}
                  >
                    {acking ? '...' : 'Confirm'}
                  </button>
                  <button
                    onClick={() => setShowNotes(false)}
                    style={{
                      background: '#374151', border: 'none',
                      color: '#9ca3af', borderRadius: 4, padding: '3px 8px',
                      fontSize: 11, cursor: 'pointer',
                    }}
                  >
                    ✕
                  </button>
                </div>
              </div>
            )}
          </div>
        )}

        {alert.acknowledged && (
          <span style={{ fontSize: 11, color: '#22c55e', whiteSpace: 'nowrap' }}>
            ✓ Ack'd
          </span>
        )}
      </div>
    </div>
  );
};

export const AlertsPanel: React.FC<Props> = ({ alerts, currentUser, onAcknowledge }) => {
  const [filter, setFilter] = useState<Severity | 'ALL'>('ALL');
  const [showAcknowledged, setShowAcknowledged] = useState(false);

  const filtered = alerts
    .filter(a => filter === 'ALL' || a.severity === filter)
    .filter(a => showAcknowledged || !a.acknowledged)
    .sort((a, b) => {
      // Sort: unacknowledged first, then by severity, then by time
      if (a.acknowledged !== b.acknowledged) return a.acknowledged ? 1 : -1;
      const sevOrder = ['CODE_BLUE', 'CRITICAL', 'ELEVATED', 'STABLE'];
      const ai = sevOrder.indexOf(a.severity);
      const bi = sevOrder.indexOf(b.severity);
      if (ai !== bi) return ai - bi;
      return new Date(b.triggeredAt).getTime() - new Date(a.triggeredAt).getTime();
    });

  const unacknowledgedCount = alerts.filter(a => !a.acknowledged).length;
  const criticalCount = alerts.filter(a =>
    !a.acknowledged && (a.severity === 'CRITICAL' || a.severity === 'CODE_BLUE')
  ).length;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      {/* Header */}
      <div style={{ padding: '12px 16px', borderBottom: '1px solid #1f2937' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <span style={{ fontSize: 14, fontWeight: 700, color: '#f9fafb' }}>ALERTS</span>
            {unacknowledgedCount > 0 && (
              <span style={{
                background: criticalCount > 0 ? '#ef444420' : '#f59e0b20',
                color:      criticalCount > 0 ? '#ef4444'   : '#f59e0b',
                border:     `1px solid ${criticalCount > 0 ? '#ef4444' : '#f59e0b'}44`,
                borderRadius: 12, padding: '1px 8px', fontSize: 11, fontWeight: 700,
              }}>
                {unacknowledgedCount} pending
              </span>
            )}
          </div>

          <label style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 11, color: '#6b7280', cursor: 'pointer' }}>
            <input
              type="checkbox"
              checked={showAcknowledged}
              onChange={e => setShowAcknowledged(e.target.checked)}
              style={{ accentColor: '#3b82f6' }}
            />
            Show acknowledged
          </label>
        </div>

        {/* Severity filter tabs */}
        <div style={{ display: 'flex', gap: 4, marginTop: 8 }}>
          {(['ALL', 'CODE_BLUE', 'CRITICAL', 'ELEVATED'] as const).map(sev => (
            <button
              key={sev}
              onClick={() => setFilter(sev)}
              style={{
                background: filter === sev
                  ? (sev === 'ALL' ? '#374151' : SEVERITY_BG[sev as Severity])
                  : 'transparent',
                border: `1px solid ${filter === sev ? (sev === 'ALL' ? '#4b5563' : SEVERITY_COLORS[sev as Severity] + '44') : '#1f2937'}`,
                color:  sev === 'ALL' ? '#9ca3af' : SEVERITY_COLORS[sev as Severity],
                borderRadius: 4, padding: '3px 8px',
                fontSize: 10, fontWeight: 600, cursor: 'pointer',
              }}
            >
              {sev}
            </button>
          ))}
        </div>
      </div>

      {/* Alert list */}
      <div style={{ flex: 1, overflow: 'auto', padding: '12px 16px' }}>
        {filtered.length === 0 ? (
          <div style={{
            textAlign: 'center', padding: 40,
            color: '#374151', fontSize: 13,
          }}>
            {unacknowledgedCount === 0 ? '✓ No active alerts' : 'No alerts match filter'}
          </div>
        ) : (
          filtered.map(alert => (
            <AlertRow
              key={alert.alertId}
              alert={alert}
              currentUser={currentUser}
              onAck={onAcknowledge}
            />
          ))
        )}
      </div>
    </div>
  );
};
