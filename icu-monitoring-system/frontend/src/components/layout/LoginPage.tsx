// src/components/layout/LoginPage.tsx
import React, { useState } from 'react';
import { api } from '../../services/api';
import { AuthUser } from '../../types';

interface Props {
  onLogin: (user: AuthUser) => void;
}

export const LoginPage: React.FC<Props> = ({ onLogin }) => {
  const [username, setUsername] = useState('admin');
  const [password, setPassword] = useState('admin123');
  const [loading,  setLoading]  = useState(false);
  const [error,    setError]    = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const user = await api.login(username, password);
      onLogin(user);
    } catch (err: any) {
      setError(err.response?.data?.message ?? 'Invalid credentials');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{
      display:        'flex', alignItems: 'center', justifyContent: 'center',
      minHeight:      '100vh',
      background:     'radial-gradient(ellipse at 20% 50%, #0f172a 0%, #030712 70%)',
      fontFamily:     'system-ui, sans-serif',
    }}>
      {/* Ambient glow */}
      <div style={{
        position: 'absolute', top: '20%', left: '10%',
        width: 400, height: 400, borderRadius: '50%',
        background: 'radial-gradient(circle, rgba(59,130,246,0.06) 0%, transparent 70%)',
        pointerEvents: 'none',
      }} />

      <div style={{
        width:      380, background: 'rgba(10,15,30,0.9)',
        border:     '1px solid #1f2937', borderRadius: 16, padding: 40,
        boxShadow:  '0 25px 50px rgba(0,0,0,0.6)',
      }}>
        {/* Logo */}
        <div style={{ textAlign: 'center', marginBottom: 32 }}>
          <div style={{ fontSize: 48, marginBottom: 8 }}>🏥</div>
          <div style={{ fontSize: 20, fontWeight: 800, color: '#f9fafb', letterSpacing: 2 }}>
            ICU MONITOR
          </div>
          <div style={{ fontSize: 12, color: '#4b5563', marginTop: 4 }}>
            Real-Time Patient Monitoring System
          </div>
        </div>

        <form onSubmit={handleSubmit}>
          <div style={{ marginBottom: 16 }}>
            <label style={{ display: 'block', fontSize: 12, color: '#6b7280', marginBottom: 6, fontWeight: 600 }}>
              USERNAME
            </label>
            <input
              type="text"
              value={username}
              onChange={e => setUsername(e.target.value)}
              required
              style={{
                width: '100%', boxSizing: 'border-box',
                background: '#0d1117', border: '1px solid #1f2937',
                borderRadius: 8, padding: '10px 14px',
                color: '#f9fafb', fontSize: 14, outline: 'none',
              }}
            />
          </div>

          <div style={{ marginBottom: 24 }}>
            <label style={{ display: 'block', fontSize: 12, color: '#6b7280', marginBottom: 6, fontWeight: 600 }}>
              PASSWORD
            </label>
            <input
              type="password"
              value={password}
              onChange={e => setPassword(e.target.value)}
              required
              style={{
                width: '100%', boxSizing: 'border-box',
                background: '#0d1117', border: '1px solid #1f2937',
                borderRadius: 8, padding: '10px 14px',
                color: '#f9fafb', fontSize: 14, outline: 'none',
              }}
            />
          </div>

          {error && (
            <div style={{
              background: 'rgba(239,68,68,0.1)', border: '1px solid #ef444444',
              color: '#f87171', borderRadius: 6, padding: '8px 12px',
              fontSize: 13, marginBottom: 16,
            }}>
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={loading}
            style={{
              width: '100%', background: loading ? '#1f2937' : '#2563eb',
              border: 'none', borderRadius: 8, padding: '12px 0',
              color: '#fff', fontSize: 14, fontWeight: 700,
              cursor: loading ? 'not-allowed' : 'pointer',
              transition: 'background 0.2s',
            }}
          >
            {loading ? 'Authenticating...' : 'Sign In'}
          </button>
        </form>

        <div style={{
          marginTop: 24, padding: '12px 14px',
          background: 'rgba(255,255,255,0.02)', borderRadius: 8,
          border: '1px solid #1f2937',
        }}>
          <div style={{ fontSize: 11, color: '#4b5563', marginBottom: 6 }}>Demo credentials:</div>
          <div style={{ fontSize: 11, color: '#6b7280', fontFamily: 'monospace' }}>
            admin / admin123 (full access)<br />
            dr.smith / admin123 (physician)<br />
            nurse.jones / admin123 (nurse)
          </div>
        </div>
      </div>
    </div>
  );
};
