export type IncidentType = 'panic' | 'fire' | 'flood' | 'accident' | 'crime' | 'medical' | 'other';
export type IncidentSeverity = 'low' | 'medium' | 'high' | 'critical';
export type IncidentStatus = 'open' | 'acknowledged' | 'responding' | 'resolved';

export interface Incident {
  id: string;
  incident_type: IncidentType;
  severity: IncidentSeverity;
  status: IncidentStatus;
  location_lat: number;
  location_lon: number;
  location_name?: string;
  commune?: string;
  description?: string;
  created_at: string;
  source: string;
}

export const INCIDENT_LABELS: Record<IncidentType, string> = {
  panic: '🚨 Panique',
  fire: '🔥 Incendie',
  flood: '💧 Inondation',
  accident: '🚗 Accident',
  crime: '⚠️ Sécurité',
  medical: '🏥 Médical',
  other: '📍 Autre',
};

export const INCIDENT_COLORS: Record<IncidentType, string> = {
  panic: '#DC2626',
  fire: '#EA580C',
  flood: '#2563EB',
  accident: '#D97706',
  crime: '#7C3AED',
  medical: '#059669',
  other: '#64748B',
};
