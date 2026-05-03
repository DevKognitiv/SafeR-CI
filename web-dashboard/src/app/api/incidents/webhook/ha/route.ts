import { NextResponse } from 'next/server';

// This endpoint receives webhooks from Home Assistant nodes
export async function POST(request: Request) {
  const payload = await request.json();
  console.log('[SafeR CI] HA Webhook received:', payload);
  
  // In production: forward to database + trigger notifications
  // For demo: just acknowledge
  return NextResponse.json({ 
    status: 'ok', 
    message: 'Incident received from HA node',
    incident_id: Date.now().toString(),
    received_at: new Date().toISOString(),
  });
}
