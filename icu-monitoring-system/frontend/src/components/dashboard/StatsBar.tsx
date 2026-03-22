// src/components/dashboard/StatsBar.tsx
import React from 'react';
import { ICUStats } from '../../types';

interface Props {
  stats:       ICUStats;
  isConnected: boolean;
}

const StatCard: React.FC<{
  label:  string;
  value:  number;
  color:  string;
  icon:   string;
  pulse?: boolean;
}> = ({ label, value, color, icon, pulse }) => (
  <div style={{
    display:        'flex',
    alignItems:     'center',
    gap:            10,
    background:     'rgba(255,255,255,0.04)',
    border:         `1px solid ${color}33`,
    borderRadius:   10,
    padding:        '10px 16px',
    position:       'relative',
    overflow:       'hidden',
  }}>
    <div style={{
      fontSize:         22,
      animation:        pulse ? 'pulse 2s ease-in-out infinite' : 'none',
    }}>
      {icon}
    </div>
    <div>
      <div style={{ fontSize: 22, fontWeight: 800, color, lineHeight: 1 }}>
        {value}
      </div>
      <div style={{ fontSize: 11, color: '#6b7280', marginTop: 2 }}>
        {label}
      </div>
    </div>
  </div>
);

export const StatsBar: React.FC<Props> = ({ stats, isConnected }) => {
  return (
    <div style={{
      display:     'flex',
      gap:         12,
      padding:     '12px 20px',
      borderBottom:'1px solid #111827',
      alignItems:  'center',
      flexWrap:    'wrap',
    }}>
      {/* Connection indicator */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginRight: 8 }}>
        <div style={{
          width: 8, height: 8, borderRadius: '50%',
          background:  isConnected ? '#22c55e' : '#ef4444',
          boxShadow:   isConnected ? '0 0 6px #22c55e' : '0 0 6px #ef4444',
          animation:   isConnected ? 'pulse 2s infinite' : 'none',
        }} />
        <span style={{ fontSize: 11, color: '#6b7280' }}>
          {isConnected ? 'LIVE' : 'DISCONNECTED'}
        </span>
      </div>

      <StatCard
        label="Active Patients"
        value={stats.activePatients}
        color="#60a5fa"
        icon="🏥"
      />
      <StatCard
        label="Critical"
        value={stats.criticalPatients}
        color="#ef4444"
        icon="⚠️"
        pulse={stats.criticalPatients > 0}
      />
      <StatCard
        label="Stable"
        value={stats.stablePatients}
        color="#22c55e"
        icon="✅"
      />
      <StatCard
        label="Pending Alerts"
        value={stats.unacknowledgedAlerts}
        color={stats.unacknowledgedAlerts > 0 ? '#f59e0b' : '#6b7280'}
        icon="🔔"
        pulse={stats.criticalAlerts > 0}
      />
      <StatCard
        label="Critical Alerts"
        value={stats.criticalAlerts}
        color={stats.criticalAlerts > 0 ? '#ef4444' : '#6b7280'}
        icon="🚨"
        pulse={stats.criticalAlerts > 0}
      />

      <div style={{ marginLeft: 'auto', textAlign: 'right' }}>
        <div style={{ fontSize: 12, color: '#374151' }}>
          {new Date().toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' })}
        </div>
        <div style={{ fontSize: 16, fontWeight: 700, color: '#9ca3af', fontFamily: 'monospace' }}>
          {new Date().toLocaleTimeString()}
        </div>
      </div>
    </div>
  );
};
