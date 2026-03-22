// src/services/api.ts – Typed HTTP client for the ICU backend API

import axios, { AxiosInstance, AxiosError } from 'axios';
import {
  Patient, Alert, VitalRecord, ICUStats, PredictionResult, AuthUser
} from '../types';

const BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:8080';

class ApiService {
  private client: AxiosInstance;

  constructor() {
    this.client = axios.create({
      baseURL: BASE_URL,
      timeout: 10_000,
      headers: { 'Content-Type': 'application/json' },
    });

    // Attach JWT token to every request
    this.client.interceptors.request.use(config => {
      const token = localStorage.getItem('icu_token');
      if (token) {
        config.headers.Authorization = `Bearer ${token}`;
      }
      return config;
    });

    // Handle auth errors globally
    this.client.interceptors.response.use(
      res => res,
      (err: AxiosError) => {
        if (err.response?.status === 401) {
          localStorage.removeItem('icu_token');
          window.location.href = '/login';
        }
        return Promise.reject(err);
      }
    );
  }

  // ── Auth ──────────────────────────────────────────────────────────────────

  async login(username: string, password: string): Promise<AuthUser> {
    const { data } = await this.client.post<AuthUser>('/api/v1/auth/login', {
      username, password,
    });
    localStorage.setItem('icu_token', data.token);
    return data;
  }

  logout() {
    localStorage.removeItem('icu_token');
  }

  // ── Patients ──────────────────────────────────────────────────────────────

  async getPatients(): Promise<Patient[]> {
    const { data } = await this.client.get<Patient[]>('/api/v1/patients');
    return data;
  }

  async getPatient(id: string): Promise<Patient> {
    const { data } = await this.client.get<Patient>(`/api/v1/patients/${id}`);
    return data;
  }

  async getCriticalPatients(): Promise<Patient[]> {
    const { data } = await this.client.get<Patient[]>('/api/v1/patients/critical');
    return data;
  }

  async admitPatient(dto: {
    patientId: string; name: string; age: number; diagnosis: string;
    bedNumber: number; priority?: number; attendingPhysician?: string; notes?: string;
  }): Promise<Patient> {
    const { data } = await this.client.post<Patient>('/api/v1/patients', dto);
    return data;
  }

  async dischargePatient(id: string): Promise<Patient> {
    const { data } = await this.client.delete<Patient>(`/api/v1/patients/${id}`);
    return data;
  }

  async getPatientStats(): Promise<ICUStats> {
    const { data } = await this.client.get<ICUStats>('/api/v1/patients/stats/summary');
    return data;
  }

  // ── Vitals ────────────────────────────────────────────────────────────────

  async getVitalsHistory(patientId: string, hours = 6): Promise<VitalRecord[]> {
    const { data } = await this.client.get<VitalRecord[]>(
      `/api/v1/patients/${patientId}/vitals`,
      { params: { hours } }
    );
    return data;
  }

  async getRecentVitals(patientId: string, count = 50): Promise<VitalRecord[]> {
    const { data } = await this.client.get<VitalRecord[]>(
      `/api/v1/patients/${patientId}/vitals/recent`,
      { params: { count } }
    );
    return data;
  }

  // ── Alerts ────────────────────────────────────────────────────────────────

  async getUnacknowledgedAlerts(): Promise<Alert[]> {
    const { data } = await this.client.get<Alert[]>('/api/v1/alerts');
    return data;
  }

  async getCriticalAlerts(): Promise<Alert[]> {
    const { data } = await this.client.get<Alert[]>('/api/v1/alerts/critical');
    return data;
  }

  async getAlertSummary(): Promise<Record<string, unknown>> {
    const { data } = await this.client.get('/api/v1/alerts/summary');
    return data;
  }

  async getPatientAlerts(patientId: string, page = 0, size = 20): Promise<{
    content: Alert[]; totalElements: number; totalPages: number;
  }> {
    const { data } = await this.client.get(
      `/api/v1/alerts/patient/${patientId}`,
      { params: { page, size } }
    );
    return data;
  }

  async acknowledgeAlert(alertId: string, acknowledgedBy: string, notes = ''): Promise<Alert> {
    const { data } = await this.client.put<Alert>(
      `/api/v1/alerts/${alertId}/acknowledge`,
      { acknowledgedBy, notes }
    );
    return data;
  }

  // ── AI Module ─────────────────────────────────────────────────────────────

  async getPrediction(patientId: string, vitals: {
    heartRate: number; systolicBp: number; diastolicBp: number;
    spo2: number; respiratoryRate: number; temperature: number;
    glucose: number; lactate: number;
  }): Promise<PredictionResult> {
    const AI_URL = process.env.REACT_APP_AI_URL || 'http://localhost:8082';
    const { data } = await axios.post<PredictionResult>(
      `${AI_URL}/api/v1/predict`,
      {
        patient_id:       patientId,
        heart_rate:       vitals.heartRate,
        systolic_bp:      vitals.systolicBp,
        diastolic_bp:     vitals.diastolicBp,
        spo2:             vitals.spo2,
        respiratory_rate: vitals.respiratoryRate,
        temperature:      vitals.temperature,
        glucose:          vitals.glucose,
        lactate:          vitals.lactate,
      },
      { timeout: 5000 }
    );
    return data;
  }

  async getRiskSummary(): Promise<{ patient_count: number; risk_distribution: Record<string, number>; high_risk_patients: Array<{ patient_id: string; deterioration_risk: number; risk_category: string }> }> {
    const AI_URL = process.env.REACT_APP_AI_URL || 'http://localhost:8082';
    const { data } = await axios.get(`${AI_URL}/api/v1/risk-summary`, { timeout: 5000 });
    return data;
  }
}

export const api = new ApiService();
export default api;
