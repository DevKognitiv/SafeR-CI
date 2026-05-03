import { NextResponse } from 'next/server';
import { MOCK_INCIDENTS } from '@/lib/mock-data';
import type { Incident } from '@/types/incident';

// In-memory store for demo incidents (resets on cold start)
let incidents: Incident[] = [...MOCK_INCIDENTS];

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const status = searchParams.get('status');
  const type = searchParams.get('incident_type');
  
  let filtered = incidents;
  if (status && status !== 'all') {
    filtered = filtered.filter(i => i.status === status);
  }
  if (type) {
    filtered = filtered.filter(i => i.incident_type === type);
  }
  
  return NextResponse.json(filtered.sort(
    (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
  ));
}

export async function POST(request: Request) {
  const body = await request.json();
  
  const newIncident: Incident = {
    id: Date.now().toString(),
    incident_type: body.incident_type || 'panic',
    severity: body.severity || 'critical',
    status: 'open',
    location_lat: body.location_lat || 5.3600,
    location_lon: body.location_lon || -4.0083,
    location_name: body.location_name || 'Position inconnue',
    commune: body.commune,
    description: body.description || 'Alerte SOS depuis l\'application web',
    created_at: new Date().toISOString(),
    source: body.source || 'web_dashboard',
  };
  
  incidents = [newIncident, ...incidents];
  
  return NextResponse.json(newIncident, { status: 201 });
}
