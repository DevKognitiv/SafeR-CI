import { timingSafeEqual } from 'crypto';
import { NextResponse } from 'next/server';
import { z } from 'zod';
import { MOCK_INCIDENTS } from '@/lib/mock-data';
import type { Incident } from '@/types/incident';

// In-memory store for demo incidents (resets on cold start)
let incidents: Incident[] = [...MOCK_INCIDENTS];

// Constant-time comparison that does not leak length via early return.
function safeEqual(a: string, b: string): boolean {
  const bufA = Buffer.from(a);
  const bufB = Buffer.from(b);
  if (bufA.length !== bufB.length) {
    timingSafeEqual(bufA, bufA);
    return false;
  }
  return timingSafeEqual(bufA, bufB);
}

// When true (demo deployments) the public SOS button may POST without a token.
const DEMO_MODE = process.env.NEXT_PUBLIC_DEMO_MODE === 'true';

// Server-only shared secret for machine callers (e.g. Home Assistant).
// Sent as  Authorization: Bearer <token>. Never NEXT_PUBLIC_.
function isAuthorized(request: Request): boolean {
  const expected = process.env.INCIDENTS_API_TOKEN;
  if (!expected) return false;
  const header = request.headers.get('authorization') ?? '';
  const provided = header.startsWith('Bearer ') ? header.slice(7) : '';
  return provided.length > 0 && safeEqual(provided, expected);
}

// Bounded, typed validation of the incident payload to prevent feed poisoning.
// Unknown keys are stripped; every field is optional (defaults applied below).
const IncidentInput = z.object({
  incident_type: z
    .enum(['panic', 'fire', 'flood', 'accident', 'crime', 'medical', 'other'])
    .optional(),
  severity: z.enum(['low', 'medium', 'high', 'critical']).optional(),
  location_lat: z.number().min(-90).max(90).optional(),
  location_lon: z.number().min(-180).max(180).optional(),
  location_name: z.string().max(200).optional(),
  commune: z.string().max(120).optional(),
  description: z.string().max(1000).optional(),
  source: z.string().max(60).optional(),
});

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
  // Require a valid token; in demo mode the public SOS button is allowed through.
  if (!isAuthorized(request) && !DEMO_MODE) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  let raw: unknown;
  try {
    raw = await request.json();
  } catch {
    return NextResponse.json({ error: 'Invalid JSON body' }, { status: 400 });
  }

  const parsed = IncidentInput.safeParse(raw);
  if (!parsed.success) {
    return NextResponse.json(
      { error: 'Invalid incident payload', details: parsed.error.flatten() },
      { status: 400 }
    );
  }
  const body = parsed.data;

  const newIncident: Incident = {
    id: Date.now().toString(),
    incident_type: body.incident_type || 'panic',
    severity: body.severity || 'critical',
    status: 'open',
    location_lat: body.location_lat ?? 5.3600,
    location_lon: body.location_lon ?? -4.0083,
    location_name: body.location_name || 'Position inconnue',
    commune: body.commune,
    description: body.description || 'Alerte SOS depuis l\'application web',
    created_at: new Date().toISOString(),
    source: body.source || 'web_dashboard',
  };

  incidents = [newIncident, ...incidents];

  return NextResponse.json(newIncident, { status: 201 });
}
