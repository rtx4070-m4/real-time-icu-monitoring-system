// src/components/dashboard/ICUDashboard.tsx
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Patient, Alert, VitalRecord, ICUStats, DashboardUpdate } from '../../types';
import { api } from '../../services/api';
import { useWebSocket } from '../../hooks/useWebSocket';
import { PatientCard } from './PatientCard';
import { StatsBar } from './StatsBar';
import { AlertsPanel } from '../alerts/AlertsPanel';
import { VitalsChart } from '../charts/VitalsChart';

interface Props {
  currentUser: string;
  onLogout:    () => void;
}

export const ICUDashboard: React.FC<Props> = ({ currentUser, onLogout }) => {
  const [patients,       setPatients]       = useState<Patient[]>([]);
  const [alerts,         setAlerts]         = useState<Alert[]>([]);
  const [selectedPatient, setSelectedPatient] = useState<Patient | null>(null);
  const [vitalsHistory,  setVitalsHistory]  = useState<VitalRecord[]>([]);
  const [stats,          setStats]          = useState<ICUStats>({
    activePatients: 0, criticalPatients: 0, stablePatients: 0,
    unacknowledgedAlerts: 0, criticalAlerts: 0,
  });
  const [loading,        setLoading]        = useState(true);
  const [rightPanel,     setRightPanel]     = useState<'alerts' | 'chart'>('alerts');

  // Live vitals per patient (keyed by patientId)
  const liveVitalsRef = useRef<Record<string, VitalRecord>>({});
  const [, forceUpdate] = useState(0);

  // ── Audio alert (critical notifications) ─────────────────────────────────
  const playAlertSound = useCallback(() => {
    try {
      const ctx = new (window.AudioContext || (window as any).webkitAudioContext)();
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.frequency.setValueAtTime(880, ctx.currentTime);
      osc.frequency.setValueAtTime(660, ctx.currentTime + 0.1);
      gain.gain.setValueAtTime(0.3, ctx.currentTime);
      gain.gain.setValueAtTime(0, ctx.currentTime + 0.3);
      osc.start(ctx.currentTime);
      osc.stop(ctx.currentTime + 0.3);
    } catch {}
  }, []);

  // ── Initial data load ──────────────────────────────────────────────────────
  useEffect(() => {
    const load = async () => {
      try {
        const [pats, alrts, patStats, alertSummary] = await Promise.allSettled([
          api.getPatients(),
          api.getUnacknowledgedAlerts(),
          api.getPatientStats(),
          api.getAlertSummary(),
        ]);

        if (pats.status === 'fulfilled')    setPatients(pats.value);
        if (alrts.status === 'fulfilled')   setAlerts(alrts.value);
        if (patStats.status === 'fulfilled') {
          const s = patStats.value as any;
          setStats(prev => ({
            ...prev,
            activePatients:   s.active_patients   ?? 0,
            criticalPatients: s.critical_patients ?? 0,
            stablePatients:   s.stable_patients   ?? 0,
          }));
        }
        if (alertSummary.status === 'fulfilled') {
          const s = alertSummary.value as any;
          setStats(prev => ({
            ...prev,
            unacknowledgedAlerts: s.unacknowledged_count ?? 0,
            criticalAlerts:       s.critical_count       ?? 0,
          }));
        }
      } finally {
        setLoading(false);
      }
    };
    load();

    // Refresh stats every 30 seconds
    const interval = setInterval(load, 30_000);
    return () => clearInterval(interval);
  }, []);

  // ── Select patient & load vitals history ───────────────────────────────────
  const handleSelectPatient = useCallback(async (patient: Patient) => {
    setSelectedPatient(patient);
    setRightPanel('chart');
    try {
      const history = await api.getVitalsHistory(patient.patientId, 2);
      setVitalsHistory(history.reverse()); // oldest first for chart
    } catch {
      setVitalsHistory([]);
    }
  }, []);

  // ── WebSocket handlers ─────────────────────────────────────────────────────
  const handleVitalsUpdate = useCallback((patientId: string, vitals: VitalRecord) => {
    liveVitalsRef.current[patientId] = vitals;

    // Append to chart if this patient is selected
    if (selectedPatient?.patientId === patientId) {
      setVitalsHistory(prev => [...prev.slice(-299), vitals]);
    }

    // Update the patient card severity
    setPatients(prev => prev.map(p =>
      p.patientId === patientId
        ? { ...p, severity: vitals.severity, latestVitals: vitals }
        : p
    ));

    forceUpdate(n => n + 1);
  }, [selectedPatient]);

  const handleAlertReceived = useCallback((alert: Alert) => {
    setAlerts(prev => {
      const exists = prev.some(a => a.alertId === alert.alertId);
      return exists ? prev : [alert, ...prev.slice(0, 199)];
    });

    if (alert.severity === 'CRITICAL' || alert.severity === 'CODE_BLUE') {
      playAlertSound();
      setStats(prev => ({
        ...prev,
        unacknowledgedAlerts: prev.unacknowledgedAlerts + 1,
        criticalAlerts: alert.severity === 'CODE_BLUE'
          ? prev.criticalAlerts + 1
          : prev.criticalAlerts,
      }));
    }
  }, [playAlertSound]);

  const handleDashboardUpdate = useCallback((update: DashboardUpdate) => {
    setPatients(prev => prev.map(p =>
      p.patientId === update.patientId
        ? { ...p, severity: update.severity }
        : p
    ));
  }, []);

  const handlePatientUpdate = useCallback((patient: Patient) => {
    setPatients(prev => {
      const exists = prev.some(p => p.patientId === patient.patientId);
      return exists
        ? prev.map(p => p.patientId === patient.patientId ? { ...p, ...patient } : p)
        : [...prev, patient];
    });
  }, []);

  const { isConnected } = useWebSocket(
    patients.map(p => p.patientId),
    {
      onVitalsUpdate:    handleVitalsUpdate,
      onAlertReceived:   handleAlertReceived,
      onDashboardUpdate: handleDashboardUpdate,
      onPatientUpdate:   handlePatientUpdate,
    }
  );

  const handleAcknowledge = useCallback((alertId: string) => {
    setAlerts(prev => prev.map(a =>
      a.alertId === alertId ? { ...a, acknowledged: true } : a
    ));
    setStats(prev => ({
      ...prev,
      unacknowledgedAlerts: Math.max(0, prev.unacknowledgedAlerts - 1),
    }));
  }, []);

  // ── Sort patients by priority / severity ───────────────────────────────────
  const sortedPatients = [...patients].sort((a, b) => {
    const sevOrder = { CODE_BLUE: 0, CRITICAL: 1, ELEVATED: 2, STABLE: 3 };
    const diff = sevOrder[a.severity] - sevOrder[b.severity];
    return diff !== 0 ? diff : a.priority - b.priority;
  });

  if (loading) {
    return (
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        height: '100vh', background: '#030712', color: '#9ca3af', flexDirection: 'column', gap: 16,
      }}>
        <div style={{
          width: 40, height: 40, borderRadius: '50%',
          border: '3px solid #1f2937', borderTopColor: '#3b82f6',
          animation: 'spin 1s linear infinite',
        }} />
        <span style={{ fontSize: 14 }}>Loading ICU Dashboard...</span>
      </div>
    );
  }

  return (
    <div style={{
      display:    'flex', flexDirection: 'column', height: '100vh',
      background: '#030712', color: '#f9fafb', fontFamily: 'system-ui, sans-serif',
      overflow:   'hidden',
    }}>
      {/* ── Top bar ──────────────────────────────────────────────────────── */}
      <div style={{
        display:      'flex', alignItems: 'center', justifyContent: 'space-between',
        padding:      '12px 20px', background: '#0a0f1e',
        borderBottom: '1px solid #111827',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <span style={{ fontSize: 22 }}>🏥</span>
          <div>
            <div style={{ fontSize: 16, fontWeight: 800, color: '#f9fafb', letterSpacing: 1 }}>
              ICU COMMAND CENTER
            </div>
            <div style={{ fontSize: 11, color: '#4b5563' }}>
              Real-Time Patient Monitoring System
            </div>
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <span style={{ fontSize: 12, color: '#6b7280' }}>
            👤 {currentUser}
          </span>
          <button
            onClick={onLogout}
            style={{
              background: 'transparent', border: '1px solid #374151',
              color: '#6b7280', borderRadius: 6, padding: '5px 12px',
              fontSize: 12, cursor: 'pointer',
            }}
          >
            Logout
          </button>
        </div>
      </div>

      {/* ── Stats bar ─────────────────────────────────────────────────────── */}
      <StatsBar stats={stats} isConnected={isConnected} />

      {/* ── Main content ──────────────────────────────────────────────────── */}
      <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>

        {/* Patient grid – left panel */}
        <div style={{
          width:      '62%', overflowY: 'auto', padding: '16px',
          borderRight:'1px solid #111827',
        }}>
          <div style={{
            fontSize: 11, color: '#4b5563', marginBottom: 12,
            textTransform: 'uppercase', letterSpacing: 1,
          }}>
            {sortedPatients.filter(p => p.active).length} Active Patients
          </div>

          <div style={{
            display:             'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))',
            gap:                 12,
          }}>
            {sortedPatients.filter(p => p.active).map(patient => (
              <PatientCard
                key={patient.patientId}
                patient={patient}
                latestVitals={liveVitalsRef.current[patient.patientId]}
                onClick={handleSelectPatient}
                isSelected={selectedPatient?.patientId === patient.patientId}
              />
            ))}
          </div>

          {sortedPatients.filter(p => p.active).length === 0 && (
            <div style={{
              textAlign: 'center', padding: 60,
              color: '#1f2937', fontSize: 14,
            }}>
              No active patients
            </div>
          )}
        </div>

        {/* Right panel – alerts or vitals chart */}
        <div style={{ width: '38%', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>

          {/* Panel toggle */}
          <div style={{
            display: 'flex', borderBottom: '1px solid #111827',
            background: '#0a0f1e',
          }}>
            {(['alerts', 'chart'] as const).map(panel => (
              <button
                key={panel}
                onClick={() => setRightPanel(panel)}
                style={{
                  flex:        1, padding:    '10px 0',
                  background:  rightPanel === panel ? 'rgba(59,130,246,0.1)' : 'transparent',
                  borderBottom: rightPanel === panel ? '2px solid #3b82f6' : '2px solid transparent',
                  color:       rightPanel === panel ? '#60a5fa' : '#4b5563',
                  border:      'none', cursor:   'pointer', fontSize: 12, fontWeight: 600,
                  textTransform: 'uppercase', letterSpacing: 0.5,
                }}
              >
                {panel === 'alerts' ? (
                  <>
                    🔔 Alerts
                    {alerts.filter(a => !a.acknowledged).length > 0 && (
                      <span style={{
                        marginLeft: 6, background: '#ef4444', color: '#fff',
                        borderRadius: 10, padding: '1px 6px', fontSize: 10,
                      }}>
                        {alerts.filter(a => !a.acknowledged).length}
                      </span>
                    )}
                  </>
                ) : '📊 Vitals Chart'}
              </button>
            ))}
          </div>

          <div style={{ flex: 1, overflow: 'hidden' }}>
            {rightPanel === 'alerts' ? (
              <AlertsPanel
                alerts={alerts}
                currentUser={currentUser}
                onAcknowledge={handleAcknowledge}
              />
            ) : selectedPatient ? (
              <div style={{ padding: 16, height: '100%', overflow: 'auto' }}>
                <div style={{ marginBottom: 12 }}>
                  <div style={{ fontSize: 14, fontWeight: 700, color: '#f9fafb' }}>
                    {selectedPatient.name}
                  </div>
                  <div style={{ fontSize: 12, color: '#6b7280' }}>
                    {selectedPatient.patientId} · Bed {selectedPatient.bedNumber} ·{' '}
                    {selectedPatient.diagnosis.replace(/_/g, ' ')}
                  </div>
                </div>

                {vitalsHistory.length > 0 ? (
                  <VitalsChart
                    records={vitalsHistory}
                    patientId={selectedPatient.patientId}
                    height={300}
                  />
                ) : (
                  <div style={{
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    height: 200, color: '#374151', fontSize: 13,
                  }}>
                    Loading vitals history...
                  </div>
                )}
              </div>
            ) : (
              <div style={{
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                height: '100%', color: '#374151', fontSize: 13, flexDirection: 'column', gap: 8,
              }}>
                <span style={{ fontSize: 32 }}>📊</span>
                Select a patient to view vitals chart
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Global CSS animations */}
      <style>{`
        @keyframes codeBluePulse {
          0%,100% { box-shadow: 0 0 10px #7c3aed44; }
          50%      { box-shadow: 0 0 25px #7c3aed88; }
        }
        @keyframes pulse {
          0%,100% { opacity: 1; }
          50%      { opacity: 0.5; }
        }
        @keyframes spin {
          to { transform: rotate(360deg); }
        }
        ::-webkit-scrollbar { width: 4px; }
        ::-webkit-scrollbar-track { background: #0a0f1e; }
        ::-webkit-scrollbar-thumb { background: #1f2937; border-radius: 2px; }
      `}</style>
    </div>
  );
};
