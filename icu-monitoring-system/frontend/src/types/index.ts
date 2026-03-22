// src/types/index.ts – All shared TypeScript types for the ICU dashboard

export type Severity = 'STABLE' | 'ELEVATED' | 'CRITICAL' | 'CODE_BLUE';
export type RiskCategory = 'LOW' | 'MODERATE' | 'HIGH' | 'IMMINENT';
export type UserRole = 'ADMIN' | 'PHYSICIAN' | 'NURSE' | 'VIEWER';

export interface VitalSigns {
  heartRate:       number;
  systolicBp:      number;
  diastolicBp:     number;
  spo2:            number;
  respiratoryRate: number;
  temperature:     number;
  glucose:         number;
  lactate:         number;
  severity:        Severity;
  news2Score?:     number;
  aiRiskScore?:    number;
  aiRiskCategory?: RiskCategory;
  timestamp:       string;
}

export interface Patient {
  id:                 number;
  patientId:          string;
  name:               string;
  age:                number;
  diagnosis:          string;
  bedNumber:          number;
  priority:           number;
  active:             boolean;
  severity:           Severity;
  admissionTime:      string;
  notes?:             string;
  attendingPhysician?:string;
  latestVitals?:      VitalSigns;
  createdAt:          string;
  updatedAt:          string;
}

export interface Alert {
  id:              number;
  alertId:         string;
  patientId:       string;
  alertType:       string;
  severity:        Severity;
  message:         string;
  vitalsHr?:       number;
  vitalsSbp?:      number;
  vitalsDbp?:      number;
  vitalsSpo2?:     number;
  vitalsRr?:       number;
  vitalsTemp?:     number;
  vitalsLac?:      number;
  triggeredAt:     string;
  acknowledged:    boolean;
  acknowledgedAt?: string;
  acknowledgedBy?: string;
  notes?:          string;
}

export interface VitalRecord extends VitalSigns {
  id:        number;
  patientId: string;
}

export interface DashboardUpdate {
  patientId:  string;
  name:       string;
  bedNumber:  number;
  severity:   Severity;
  heartRate:  number;
  spo2:       number;
  systolicBp: number;
  news2:      number;
  timestamp:  string;
}

export interface ICUStats {
  activePatients:   number;
  criticalPatients: number;
  stablePatients:   number;
  unacknowledgedAlerts: number;
  criticalAlerts:   number;
}

export interface AuthUser {
  token:    string;
  username: string;
  role:     UserRole;
  fullName: string;
}

export interface PredictionResult {
  patientId:           string;
  deteriorationRisk:   number;
  riskCategory:        RiskCategory;
  predictedEventHours: number | null;
  confidence:          number;
  featureImportances:  Record<string, number>;
  timestamp:           string;
}

// WebSocket message types
export type WsMessage =
  | { type: 'VITALS';    patientId: string; data: VitalRecord }
  | { type: 'ALERT';     data: Alert }
  | { type: 'DASHBOARD'; data: DashboardUpdate }
  | { type: 'PATIENT';   data: Patient };

export const SEVERITY_COLORS: Record<Severity, string> = {
  STABLE:    '#22c55e',
  ELEVATED:  '#f59e0b',
  CRITICAL:  '#ef4444',
  CODE_BLUE: '#7c3aed',
};

export const SEVERITY_BG: Record<Severity, string> = {
  STABLE:    'rgba(34,197,94,0.15)',
  ELEVATED:  'rgba(245,158,11,0.15)',
  CRITICAL:  'rgba(239,68,68,0.15)',
  CODE_BLUE: 'rgba(124,58,237,0.20)',
};

export const RISK_COLORS: Record<RiskCategory, string> = {
  LOW:      '#22c55e',
  MODERATE: '#f59e0b',
  HIGH:     '#ef4444',
  IMMINENT: '#7c3aed',
};

export const VITAL_NORMAL_RANGES = {
  heartRate:       { min: 60,  max: 100, unit: 'bpm'          },
  systolicBp:      { min: 90,  max: 140, unit: 'mmHg'         },
  diastolicBp:     { min: 60,  max: 90,  unit: 'mmHg'         },
  spo2:            { min: 95,  max: 100, unit: '%'             },
  respiratoryRate: { min: 12,  max: 20,  unit: 'br/min'       },
  temperature:     { min: 36,  max: 37.5,unit: '°C'           },
  glucose:         { min: 70,  max: 140, unit: 'mg/dL'        },
  lactate:         { min: 0.5, max: 2.0, unit: 'mmol/L'       },
} as const;
