'use client';

import { useMemo } from 'react';

/* ---------- Sample HA-shaped entities (drives the same layout the Flutter
   dashboard will consume from a real HA WebSocket). ---------- */

type Entity = {
  id: string;
  name: string;
  domain: string;
  state: string;
  isOn?: boolean;
  unit?: string;
  brightness?: number; // 0..255
  area: string;
};

const SAMPLE: Entity[] = [
  // Living room
  { id: 'light.living_floor', name: 'Floor lamp', domain: 'light', state: 'on', isOn: true, brightness: 178, area: 'Living room' },
  { id: 'light.living_spotlights', name: 'Spotlights', domain: 'light', state: 'on', isOn: true, brightness: 125, area: 'Living room' },
  { id: 'media_player.living_sonos', name: 'Sonos', domain: 'media_player', state: 'playing', isOn: true, area: 'Living room' },
  { id: 'cover.living_blinds', name: 'Blinds', domain: 'cover', state: 'open', isOn: true, area: 'Living room' },
  { id: 'climate.living_thermostat', name: 'Thermostat', domain: 'climate', state: 'heat', isOn: true, area: 'Living room' },
  // Kitchen
  { id: 'light.kitchen', name: 'Worktop', domain: 'light', state: 'off', isOn: false, area: 'Kitchen' },
  { id: 'sensor.fridge', name: 'Fridge', domain: 'sensor', state: '4.1', unit: '°C', area: 'Kitchen' },
  { id: 'switch.kettle', name: 'Kettle', domain: 'switch', state: 'off', isOn: false, area: 'Kitchen' },
  // Bedroom
  { id: 'light.bedroom', name: 'Bedside', domain: 'light', state: 'off', isOn: false, area: 'Bedroom' },
  { id: 'fan.bedroom', name: 'Ceiling fan', domain: 'fan', state: 'off', isOn: false, area: 'Bedroom' },
  // Entryway
  { id: 'lock.front_door', name: 'Front door', domain: 'lock', state: 'locked', isOn: false, area: 'Entryway' },
  { id: 'alarm_control_panel.home', name: 'Alarm', domain: 'alarm_control_panel', state: 'armed_home', isOn: true, area: 'Entryway' },
  { id: 'camera.porch', name: 'Porch cam', domain: 'camera', state: 'streaming', isOn: true, area: 'Entryway' },
  // Outside
  { id: 'cover.garage', name: 'Garage', domain: 'cover', state: 'closed', isOn: false, area: 'Outside' },
  { id: 'vacuum.roomba', name: 'Roomba', domain: 'vacuum', state: 'docked', isOn: false, area: 'Outside' },
];

const TEMP = { value: 21.4, unit: '°C' };
const HUM = { value: 47, unit: '%' };
const PEOPLE = [
  { name: 'Amara', state: 'home' },
  { name: 'Yann', state: 'away' },
];

/* ---------- Aurora design tokens ---------- */

const ACCENT: Record<string, string> = {
  light: '#FBBF24',
  switch: '#60A5FA',
  fan: '#60A5FA',
  cover: '#A78BFA',
  climate: '#F87171',
  media_player: '#C084FC',
  lock: '#F59E0B',
  alarm_control_panel: '#EF4444',
  camera: '#94A3B8',
  sensor: '#34D399',
  binary_sensor: '#34D399',
  vacuum: '#2DD4BF',
};
const accentOf = (d: string) => ACCENT[d] ?? '#818CF8';

function iconFor(domain: string): string {
  // Lucide-equivalent SVG strings inlined to avoid any extra dep.
  switch (domain) {
    case 'light': return 'M9 18h6M10 22h4M12 2a7 7 0 0 0-4 12.7c.9.7 1.4 1.7 1.4 2.8V18h5.2v-.5c0-1.1.5-2.1 1.4-2.8A7 7 0 0 0 12 2z';
    case 'switch': return 'M8 12h8M12 8v8M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0z';
    case 'fan': return 'M12 12c0-3 2-5 5-5 1.5 0 2.5 1 2.5 2 0 2-2 4-7.5 3zM12 12c3 0 5 2 5 5 0 1.5-1 2.5-2 2.5-2 0-4-2-3-7.5zM12 12c0 3-2 5-5 5-1.5 0-2.5-1-2.5-2 0-2 2-4 7.5-3zM12 12c-3 0-5-2-5-5 0-1.5 1-2.5 2-2.5 2 0 4 2 3 7.5z';
    case 'cover': return 'M4 4h16v4H4zM4 8v12M20 8v12M4 14h16M4 20h16';
    case 'climate': return 'M14 14.76V3.5a2.5 2.5 0 0 0-5 0v11.26a4.5 4.5 0 1 0 5 0z';
    case 'media_player': return 'M9 18V5l12-2v13M9 18a3 3 0 1 1-6 0 3 3 0 0 1 6 0zM21 16a3 3 0 1 1-6 0 3 3 0 0 1 6 0z';
    case 'lock': return 'M5 11h14v10H5zM8 11V7a4 4 0 0 1 8 0v4';
    case 'alarm_control_panel': return 'M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z';
    case 'camera': return 'M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2zM12 17a4 4 0 1 0 0-8 4 4 0 0 0 0 8z';
    case 'sensor': case 'binary_sensor': return 'M3 12h4l3-9 4 18 3-9h4';
    case 'vacuum': return 'M12 2a10 10 0 1 0 10 10A10 10 0 0 0 12 2zm0 14a4 4 0 1 1 4-4 4 4 0 0 1-4 4z';
    default: return 'M4 4h16v16H4z';
  }
}

function stateLabel(e: Entity): string {
  if (e.domain === 'light' && e.isOn && e.brightness != null) {
    return `${Math.round((e.brightness / 255) * 100)}%`;
  }
  if (e.unit) return `${e.state} ${e.unit}`;
  return e.state.replaceAll('_', ' ');
}

/* ---------- Page ---------- */

export default function AuroraPage() {
  const grouped = useMemo(() => {
    const by: Record<string, Entity[]> = {};
    for (const e of SAMPLE) (by[e.area] ??= []).push(e);
    return by;
  }, []);

  const activeCount = SAMPLE.filter((e) => e.isOn).length;
  const lightsOn = SAMPLE.filter((e) => e.domain === 'light' && e.isOn).length;

  return (
    <div className="min-h-screen relative overflow-hidden text-white"
         style={{ fontFamily: 'Inter, system-ui, sans-serif',
                  background: 'linear-gradient(135deg, #06081C 0%, #0E1138 45%, #1B0838 100%)' }}>
      {/* Aurora washes */}
      <div className="pointer-events-none absolute -top-32 -right-24 h-[520px] w-[520px] rounded-full blur-3xl opacity-50"
           style={{ background: 'radial-gradient(circle, #14B8A6 0%, transparent 60%)' }} />
      <div className="pointer-events-none absolute -bottom-40 -left-24 h-[560px] w-[560px] rounded-full blur-3xl opacity-40"
           style={{ background: 'radial-gradient(circle, #F59E0B 0%, transparent 60%)' }} />
      <div className="pointer-events-none absolute top-1/3 left-1/2 h-[420px] w-[420px] -translate-x-1/2 rounded-full blur-3xl opacity-25"
           style={{ background: 'radial-gradient(circle, #818CF8 0%, transparent 65%)' }} />

      <main className="relative max-w-6xl mx-auto px-6 pt-8 pb-16">
        <TopBar />
        <Hero
          temp={TEMP} hum={HUM} active={activeCount} lightsOn={lightsOn}
          people={PEOPLE} />
        <StatusChipsRow temp={TEMP} hum={HUM} people={PEOPLE} />

        <div className="mt-10 space-y-9">
          {Object.entries(grouped).map(([area, ents]) => (
            <AreaSection key={area} area={area} entities={ents} />
          ))}
        </div>

        <ActivityStrip
          events={SAMPLE.filter((e) => e.isOn).slice(0, 14).map((e, i) => ({
            id: `${e.id}-${i}`,
            color: accentOf(e.domain),
            label: `${e.name} · ${stateLabel(e)}`,
          }))}
        />
      </main>
    </div>
  );
}

/* ---------- Top bar ---------- */
function TopBar() {
  return (
    <header className="flex items-center justify-between">
      <div className="flex items-center gap-3">
        <div className="h-9 w-9 rounded-xl grid place-items-center border border-white/10"
             style={{ background: 'linear-gradient(135deg, #14B8A6, #818CF8)' }}>
          <span className="text-[15px] font-semibold">S</span>
        </div>
        <div>
          <div className="text-[15px] font-semibold tracking-tight">SafeR Home</div>
          <div className="text-[11px] uppercase tracking-[0.18em] text-white/40">Aurora preview</div>
        </div>
      </div>
      <div className="flex items-center gap-2 text-[12px] text-white/70">
        <span className="relative inline-flex h-2 w-2">
          <span className="absolute inline-flex h-full w-full rounded-full opacity-60 animate-ping"
                style={{ background: '#34D399' }} />
          <span className="relative inline-flex rounded-full h-2 w-2" style={{ background: '#34D399' }} />
        </span>
        Connected — Home Assistant
      </div>
    </header>
  );
}

/* ---------- Hero: Home pulse ---------- */
function Hero(props: { temp: typeof TEMP; hum: typeof HUM; active: number; lightsOn: number; people: typeof PEOPLE }) {
  const homeCount = props.people.filter((p) => p.state === 'home').length;
  const calm = props.active <= 6 && homeCount > 0;
  return (
    <section className="mt-7 rounded-[26px] p-7 relative overflow-hidden"
             style={{ background: 'rgba(255,255,255,0.04)',
                      border: '1px solid rgba(255,255,255,0.08)',
                      backdropFilter: 'blur(18px)' }}>
      <div className="absolute -top-24 -right-24 h-72 w-72 rounded-full blur-3xl opacity-50"
           style={{ background: 'radial-gradient(circle, #14B8A6 0%, transparent 60%)' }} />
      <div className="relative flex flex-col md:flex-row items-start gap-8">
        {/* Breathing ring */}
        <div className="relative shrink-0">
          <div className="h-[170px] w-[170px] rounded-full grid place-items-center relative"
               style={{ background: 'conic-gradient(from 220deg, #14B8A6 0deg, #818CF8 180deg, #F59E0B 320deg, #14B8A6 360deg)' }}>
            <div className="absolute inset-[5px] rounded-full" style={{ background: '#0A0E2A' }} />
            <div className="relative text-center">
              <div className="text-[11px] uppercase tracking-[0.2em] text-white/40">Home pulse</div>
              <div className="text-[44px] leading-none mt-1 font-semibold"
                   style={{ fontFamily: '"Space Grotesk", Inter, sans-serif' }}>
                {calm ? 'Calm' : 'Active'}
              </div>
              <div className="text-[12px] text-white/55 mt-1">{props.active} devices live</div>
            </div>
          </div>
          {/* Outer breathing halo */}
          <div className="absolute inset-0 rounded-full -z-10 animate-[pulse_5s_ease-in-out_infinite]"
               style={{ background: 'radial-gradient(circle, rgba(20,184,166,0.25), transparent 65%)', filter: 'blur(20px)' }} />
        </div>

        <div className="flex-1 grid grid-cols-2 gap-5 w-full">
          <PulseStat label="Indoor" value={`${props.temp.value}`} unit={props.temp.unit} caption="Living room" tint="#F87171" />
          <PulseStat label="Humidity" value={`${props.hum.value}`} unit={props.hum.unit} caption="comfortable" tint="#60A5FA" />
          <PulseStat label="Lights on" value={`${props.lightsOn}`} unit="" caption="across 3 areas" tint="#FBBF24" />
          <PulseStat label="At home" value={`${homeCount}`} unit={`/ ${props.people.length}`} caption="Amara" tint="#34D399" />
        </div>
      </div>
    </section>
  );
}

function PulseStat({ label, value, unit, caption, tint }:
                   { label: string; value: string; unit: string; caption: string; tint: string }) {
  return (
    <div className="rounded-2xl px-4 py-3 border border-white/10 relative overflow-hidden"
         style={{ background: 'rgba(255,255,255,0.025)' }}>
      <div className="absolute inset-y-0 left-0 w-[3px]" style={{ background: tint, opacity: 0.7 }} />
      <div className="text-[10px] uppercase tracking-[0.18em] text-white/40">{label}</div>
      <div className="mt-1 flex items-baseline gap-1">
        <span className="text-[28px] leading-none font-semibold"
              style={{ fontFamily: '"Space Grotesk", Inter, sans-serif' }}>{value}</span>
        <span className="text-[13px] text-white/55">{unit}</span>
      </div>
      <div className="text-[11px] text-white/45 mt-1">{caption}</div>
    </div>
  );
}

/* ---------- Status chips row ---------- */
function StatusChipsRow(props: { temp: typeof TEMP; hum: typeof HUM; people: typeof PEOPLE }) {
  return (
    <div className="mt-5 flex flex-wrap gap-2">
      <Chip color="#F87171" label={`${props.temp.value}${props.temp.unit}`} icon="thermometer" />
      <Chip color="#60A5FA" label={`${props.hum.value}${props.hum.unit}`} icon="droplet" />
      <Chip color="#34D399" label="All clear" icon="shield" />
      {props.people.map((p) => (
        <Chip key={p.name} color={p.state === 'home' ? '#34D399' : '#94A3B8'} label={`${p.name} · ${p.state}`} icon="user" />
      ))}
    </div>
  );
}

function Chip({ color, label, icon }: { color: string; label: string; icon: string }) {
  const d = icon === 'thermometer'
    ? 'M14 14.76V3.5a2.5 2.5 0 0 0-5 0v11.26a4.5 4.5 0 1 0 5 0z'
    : icon === 'droplet'
    ? 'M12 3.5l5 7.4a6 6 0 1 1-10 0z'
    : icon === 'shield'
    ? 'M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z'
    : 'M16 21v-2a4 4 0 0 0-8 0v2M12 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8z';
  return (
    <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full text-[12.5px]"
         style={{ background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.08)' }}>
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2"
           strokeLinecap="round" strokeLinejoin="round"><path d={d} /></svg>
      <span className="text-white/85">{label}</span>
    </div>
  );
}

/* ---------- Area + tiles ---------- */
function AreaSection({ area, entities }: { area: string; entities: Entity[] }) {
  return (
    <section>
      <div className="flex items-baseline justify-between mb-3">
        <h3 className="text-[15px] font-semibold tracking-tight">{area}</h3>
        <span className="text-[10px] uppercase tracking-[0.18em] text-white/40">
          {entities.filter((e) => e.isOn).length} active · {entities.length} devices
        </span>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
        {entities.map((e) => <EntityTile key={e.id} entity={e} />)}
      </div>
    </section>
  );
}

function EntityTile({ entity }: { entity: Entity }) {
  const accent = accentOf(entity.domain);
  const on = !!entity.isOn;
  return (
    <div className="relative rounded-[18px] p-4 overflow-hidden transition-transform hover:-translate-y-0.5"
         style={{
           background: on
             ? `linear-gradient(160deg, rgba(255,255,255,0.06), rgba(255,255,255,0.02))`
             : 'rgba(255,255,255,0.025)',
           border: `1px solid ${on ? 'rgba(255,255,255,0.12)' : 'rgba(255,255,255,0.06)'}`,
           backdropFilter: 'blur(14px)',
           boxShadow: on ? `0 0 0 1px ${accent}22 inset, 0 14px 30px -18px ${accent}80` : 'none',
         }}>
      {on && (
        <div className="absolute -top-12 -right-10 h-32 w-32 rounded-full blur-2xl opacity-50"
             style={{ background: `radial-gradient(circle, ${accent}, transparent 65%)` }} />
      )}
      <div className="relative flex items-center justify-between">
        <div className="h-10 w-10 rounded-xl grid place-items-center"
             style={{
               background: on ? `${accent}22` : 'rgba(255,255,255,0.05)',
               border: `1px solid ${on ? accent + '44' : 'rgba(255,255,255,0.08)'}`,
             }}>
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none"
               stroke={on ? accent : 'rgba(255,255,255,0.55)'} strokeWidth="1.8"
               strokeLinecap="round" strokeLinejoin="round">
            <path d={iconFor(entity.domain)} />
          </svg>
        </div>
        {on && (
          <span className="text-[10px] uppercase tracking-[0.15em] px-2 py-1 rounded-full"
                style={{ color: accent, background: `${accent}14`, border: `1px solid ${accent}33` }}>
            live
          </span>
        )}
      </div>
      <div className="relative mt-4">
        <div className="text-[14.5px] font-semibold tracking-tight">{entity.name}</div>
        <div className="text-[12px] text-white/55 mt-0.5">{stateLabel(entity)}</div>
      </div>
      {entity.domain === 'light' && on && entity.brightness != null && (
        <div className="relative mt-3 h-[3px] rounded-full overflow-hidden"
             style={{ background: 'rgba(255,255,255,0.08)' }}>
          <div className="h-full rounded-full"
               style={{ width: `${(entity.brightness / 255) * 100}%`,
                        background: `linear-gradient(90deg, ${accent}66, ${accent})` }} />
        </div>
      )}
    </div>
  );
}

/* ---------- Activity strip ---------- */
function ActivityStrip({ events }: { events: { id: string; color: string; label: string }[] }) {
  return (
    <section className="mt-10 rounded-2xl px-4 py-3"
             style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.06)' }}>
      <div className="flex items-center justify-between">
        <div className="text-[10px] uppercase tracking-[0.2em] text-white/40">Live activity</div>
        <div className="text-[11px] text-white/40">{events.length} events · last 5 min</div>
      </div>
      <div className="mt-3 flex items-center gap-1.5">
        {events.map((ev, i) => (
          <div key={ev.id} className="h-2 rounded-full"
               style={{
                 width: `${24 - i * 1}px`,
                 background: ev.color,
                 opacity: 1 - i * 0.05,
                 boxShadow: i < 3 ? `0 0 10px ${ev.color}` : 'none',
               }} />
        ))}
      </div>
      <div className="mt-2 text-[12px] text-white/55 truncate">
        Latest · {events[0]?.label ?? 'all quiet'}
      </div>
    </section>
  );
}
