import { NextResponse } from 'next/server';

// Server-side base URL for the SafeR FastAPI backend. Kept off
// NEXT_PUBLIC_* so it stays a server secret in production. Falls back
// to the public var for convenience in local dev.
const API_BASE =
  process.env.SAFER_API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

export const dynamic = 'force-dynamic';

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  // Forward filters the backend understands.
  const out = new URLSearchParams();
  for (const k of ['status', 'incident_type', 'lat', 'lon', 'radius_km', 'limit', 'offset']) {
    const v = searchParams.get(k);
    if (v !== null) out.set(k, v);
  }
  const upstream = `${API_BASE}/api/v1/incidents/?${out.toString()}`;
  try {
    const res = await fetch(upstream, { cache: 'no-store' });
    if (!res.ok) {
      return NextResponse.json(
        { error: 'upstream', status: res.status, detail: await safeText(res) },
        { status: 502 },
      );
    }
    return NextResponse.json(await res.json());
  } catch (e: unknown) {
    return NextResponse.json(
      { error: 'unreachable', detail: (e as Error).message, upstream },
      { status: 503 },
    );
  }
}

export async function POST(request: Request) {
  const body = await request.text(); // pass through opaquely
  const upstream = `${API_BASE}/api/v1/incidents/`;
  try {
    const res = await fetch(upstream, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body,
      cache: 'no-store',
    });
    const payload = await res.json().catch(() => ({}));
    return NextResponse.json(payload, { status: res.status });
  } catch (e: unknown) {
    return NextResponse.json(
      { error: 'unreachable', detail: (e as Error).message, upstream },
      { status: 503 },
    );
  }
}

async function safeText(res: Response): Promise<string> {
  try { return await res.text(); } catch { return ''; }
}
