import { timingSafeEqual } from 'crypto';
import { NextResponse } from 'next/server';

// Constant-time string comparison that does not leak length via early return.
function safeEqual(a: string, b: string): boolean {
  const bufA = Buffer.from(a);
  const bufB = Buffer.from(b);
  if (bufA.length !== bufB.length) {
    // Compare against self to keep timing uniform, then fail.
    timingSafeEqual(bufA, bufA);
    return false;
  }
  return timingSafeEqual(bufA, bufB);
}

// This endpoint receives webhooks from Home Assistant nodes
export async function POST(request: Request) {
  const expected = process.env.HA_WEBHOOK_SECRET;
  if (!expected) {
    // Fail closed when the secret is not configured on the server.
    return NextResponse.json({ error: 'Webhook not configured' }, { status: 503 });
  }

  const provided = request.headers.get('x-ha-webhook-secret') ?? '';
  if (!safeEqual(provided, expected)) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  // Consume the body but do not log it (contains victim GPS/PII).
  await request.json();
  console.log('[SafeR CI] HA Webhook received (authenticated)');

  // In production: forward to database + trigger notifications
  // For demo: just acknowledge
  return NextResponse.json({
    status: 'ok',
    message: 'Incident received from HA node',
    incident_id: Date.now().toString(),
    received_at: new Date().toISOString(),
  });
}
