// src/hooks/useWebSocket.ts – SockJS + STOMP WebSocket connection to backend

import { useEffect, useRef, useCallback, useState } from 'react';
import SockJS from 'sockjs-client';
import { Client, StompSubscription } from '@stomp/stompjs';
import { Alert, Patient, VitalRecord, DashboardUpdate } from '../types';

const WS_URL = process.env.REACT_APP_WS_URL || 'http://localhost:8080';

interface UseWebSocketOptions {
  onVitalsUpdate?:    (patientId: string, vitals: VitalRecord) => void;
  onAlertReceived?:   (alert: Alert) => void;
  onCriticalAlert?:   (alert: Alert) => void;
  onDashboardUpdate?: (update: DashboardUpdate) => void;
  onPatientUpdate?:   (patient: Patient) => void;
  onConnected?:       () => void;
  onDisconnected?:    () => void;
}

interface UseWebSocketReturn {
  isConnected: boolean;
  connectionError: string | null;
  disconnect: () => void;
}

export function useWebSocket(
  patientIds: string[],
  options: UseWebSocketOptions
): UseWebSocketReturn {
  const clientRef = useRef<Client | null>(null);
  const subsRef   = useRef<StompSubscription[]>([]);
  const [isConnected,    setIsConnected]    = useState(false);
  const [connectionError, setConnectionError] = useState<string | null>(null);

  const disconnect = useCallback(() => {
    subsRef.current.forEach(sub => { try { sub.unsubscribe(); } catch {} });
    subsRef.current = [];
    if (clientRef.current?.active) {
      clientRef.current.deactivate();
    }
    setIsConnected(false);
  }, []);

  useEffect(() => {
    const token = localStorage.getItem('icu_token');

    const client = new Client({
      webSocketFactory: () => new SockJS(`${WS_URL}/ws`),
      connectHeaders:   token ? { Authorization: `Bearer ${token}` } : {},
      reconnectDelay:   3000,
      heartbeatIncoming: 10_000,
      heartbeatOutgoing: 10_000,

      onConnect: () => {
        setIsConnected(true);
        setConnectionError(null);
        options.onConnected?.();

        const subs: StompSubscription[] = [];

        // Subscribe to global dashboard updates
        subs.push(client.subscribe('/topic/dashboard', msg => {
          try {
            const update: DashboardUpdate = JSON.parse(msg.body);
            options.onDashboardUpdate?.(update);
          } catch {}
        }));

        // Subscribe to all alerts
        subs.push(client.subscribe('/topic/alerts', msg => {
          try {
            const alert: Alert = JSON.parse(msg.body);
            options.onAlertReceived?.(alert);
          } catch {}
        }));

        // Critical alert channel
        subs.push(client.subscribe('/topic/alerts/critical', msg => {
          try {
            const alert: Alert = JSON.parse(msg.body);
            options.onCriticalAlert?.(alert);
          } catch {}
        }));

        // Patient registry updates
        subs.push(client.subscribe('/topic/patients', msg => {
          try {
            const patient: Patient = JSON.parse(msg.body);
            options.onPatientUpdate?.(patient);
          } catch {}
        }));

        // Per-patient vitals streams
        patientIds.forEach(pid => {
          subs.push(client.subscribe(`/topic/vitals/${pid}`, msg => {
            try {
              const vitals: VitalRecord = JSON.parse(msg.body);
              options.onVitalsUpdate?.(pid, vitals);
            } catch {}
          }));
        });

        subsRef.current = subs;
      },

      onStompError: frame => {
        setConnectionError(`WebSocket error: ${frame.headers['message']}`);
        setIsConnected(false);
      },

      onDisconnect: () => {
        setIsConnected(false);
        options.onDisconnected?.();
      },

      onWebSocketError: (error) => {
        setConnectionError(`Connection failed: ${error.message}`);
        setIsConnected(false);
      },
    });

    client.activate();
    clientRef.current = client;

    return () => {
      disconnect();
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [patientIds.join(',')]);

  return { isConnected, connectionError, disconnect };
}
