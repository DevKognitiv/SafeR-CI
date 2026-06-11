'use client';

import * as React from 'react';
import Link from 'next/link';
import { useI18n, useSettings, useStore, useTokens } from './providers';
import { accentOf, AREA_KEYS, AreaKey, Entity, isAreaKey } from './data';
import { DomainIcon } from './icons';
import { GlassCard } from './shell';

/* ---------- Home Pulse hero ---------- */
export function HomePulse({ activeCount, lightsOn, areasCount, peopleHome, peopleTotal, temp, hum }:
                          { activeCount: number; lightsOn: number; areasCount: number;
                            peopleHome: number; peopleTotal: number;
                            temp: { value: number; unit: string }; hum: { value: number; unit: string } }) {
  const t = useTokens();
  const { t: tr } = useI18n();
  const calm = activeCount <= 6 && peopleHome > 0;
  return (
    <GlassCard className="mt-7 p-7 relative overflow-hidden">
      <div className="absolute -top-24 -right-24 h-72 w-72 rounded-full blur-3xl opacity-50"
           style={{ background: `radial-gradient(circle, ${t.washes[0]} 0%, transparent 60%)` }} />
      <div className="relative flex flex-col md:flex-row items-start gap-8">
        <div className="relative shrink-0 mx-auto md:mx-0">
          <div className="h-[170px] w-[170px] rounded-full grid place-items-center relative"
               style={{ background: `conic-gradient(from 220deg, ${t.washes[0]} 0deg, ${t.washes[2]} 180deg, ${t.washes[1]} 320deg, ${t.washes[0]} 360deg)` }}>
            <div className="absolute inset-[5px] rounded-full"
                 style={{ background: t.mode === 'dark' ? '#0A0E2A' : '#FFFFFF' }} />
            <div className="relative text-center">
              <div className="text-[11px] uppercase tracking-[0.2em]" style={{ color: t.textFaint }}>{tr('pulse.title')}</div>
              <div className="text-[44px] leading-none mt-1 font-semibold"
                   style={{ fontFamily: '"Space Grotesk", Inter, sans-serif' }}>
                {calm ? tr('pulse.calm') : tr('pulse.active')}
              </div>
              <div className="text-[12px] mt-1" style={{ color: t.textSubtle }}>
                {tr('pulse.devicesLive', { n: activeCount })}
              </div>
            </div>
          </div>
          <div className="absolute inset-0 rounded-full -z-10 animate-[pulse_5s_ease-in-out_infinite]"
               style={{ background: `radial-gradient(circle, ${t.washes[0]}40, transparent 65%)`, filter: 'blur(20px)' }} />
        </div>
        <div className="flex-1 grid grid-cols-2 gap-5 w-full">
          <PulseStat label={tr('pulse.indoor')} value={`${temp.value}`} unit={temp.unit} caption="Living" tint="#F87171" />
          <PulseStat label={tr('pulse.humidity')} value={`${hum.value}`} unit={hum.unit} caption="" tint="#60A5FA" />
          <PulseStat label={tr('pulse.lightsOn')} value={`${lightsOn}`} unit=""
                     caption={tr('pulse.acrossAreas', { n: areasCount })} tint="#FBBF24" />
          <PulseStat label={tr('pulse.atHome')} value={`${peopleHome}`} unit={`/ ${peopleTotal}`} caption="" tint="#34D399" />
        </div>
      </div>
    </GlassCard>
  );
}

function PulseStat({ label, value, unit, caption, tint }:
                   { label: string; value: string; unit: string; caption: string; tint: string }) {
  const t = useTokens();
  return (
    <div className="rounded-2xl px-4 py-3 relative overflow-hidden"
         style={{ background: t.mode === 'dark' ? 'rgba(255,255,255,0.025)' : 'rgba(255,255,255,0.5)',
                  border: `1px solid ${t.glassBorder}` }}>
      <div className="absolute inset-y-0 left-0 w-[3px]" style={{ background: tint, opacity: 0.7 }} />
      <div className="text-[10px] uppercase tracking-[0.18em]" style={{ color: t.textFaint }}>{label}</div>
      <div className="mt-1 flex items-baseline gap-1">
        <span className="text-[28px] leading-none font-semibold"
              style={{ fontFamily: '"Space Grotesk", Inter, sans-serif' }}>{value}</span>
        <span className="text-[13px]" style={{ color: t.textSubtle }}>{unit}</span>
      </div>
      {caption && <div className="text-[11px] mt-1" style={{ color: t.textFaint }}>{caption}</div>}
    </div>
  );
}

/* ---------- Status chips row ---------- */
export function StatusChips({ temp, hum, people }:
                            { temp: { value: number; unit: string };
                              hum: { value: number; unit: string };
                              people: { name: string; state: string }[] }) {
  const { t: tr } = useI18n();
  return (
    <div className="mt-5 flex flex-wrap gap-2">
      <Chip color="#F87171" label={`${temp.value}${temp.unit}`} icon="thermometer" />
      <Chip color="#60A5FA" label={`${hum.value}${hum.unit}`} icon="droplet" />
      <Chip color="#34D399" label={tr('chips.allClear')} icon="shield" />
      {people.map((p) => (
        <Chip key={p.name} color={p.state === 'home' ? '#34D399' : '#94A3B8'}
              label={`${p.name} · ${tr(p.state === 'home' ? 'state.home' : 'state.away')}`} icon="user" />
      ))}
    </div>
  );
}

function Chip({ color, label, icon }: { color: string; label: string; icon: string }) {
  const t = useTokens();
  return (
    <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full text-[12.5px]"
         style={{ background: t.glass, border: `1px solid ${t.glassBorder}`, color: t.text }}>
      <DomainIcon name={icon} size={14} color={color} strokeWidth={2} />
      <span>{label}</span>
    </div>
  );
}

/* ---------- Area section ---------- */
export function AreaSection({ areaKey, entities, onEntity }:
                            { areaKey: AreaKey; entities: Entity[];
                              onEntity: (id: string) => void }) {
  const { t: tr } = useI18n();
  const t = useTokens();
  const active = entities.filter(e => e.isOn).length;
  return (
    <section>
      <div className="flex items-baseline justify-between mb-3">
        <Link href={`/aurora/areas/${areaKey}`}
              className="group inline-flex items-baseline gap-2"
              style={{ color: t.text }}>
          <h3 className="text-[15px] font-semibold tracking-tight">{tr(`area.${areaKey}`)}</h3>
          <span className="opacity-50 group-hover:opacity-100 transition-opacity">
            <DomainIcon name="chevronRight" size={14} />
          </span>
        </Link>
        <span className="text-[10px] uppercase tracking-[0.18em]" style={{ color: t.textFaint }}>
          {active} {tr('area.active')} · {entities.length} {tr('area.devices')}
        </span>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
        {entities.map(e => <EntityTile key={e.id} entity={e} onClick={() => onEntity(e.id)} />)}
      </div>
    </section>
  );
}

/* ---------- Entity tile ---------- */
export function EntityTile({ entity, onClick }: { entity: Entity; onClick: () => void }) {
  const t = useTokens();
  const { t: tr } = useI18n();
  const accent = accentOf(entity.domain);
  const on = entity.isOn;
  return (
    <button onClick={onClick}
            className="text-left relative rounded-[18px] p-4 overflow-hidden transition-all hover:-translate-y-0.5 active:scale-[0.98]"
            style={{
              background: on
                ? (t.mode === 'dark'
                    ? 'linear-gradient(160deg, rgba(255,255,255,0.06), rgba(255,255,255,0.02))'
                    : 'linear-gradient(160deg, rgba(255,255,255,0.85), rgba(255,255,255,0.55))')
                : t.glass,
              border: `1px solid ${on ? t.activeBorder : t.glassBorder}`,
              backdropFilter: 'blur(14px)',
              boxShadow: on ? `0 0 0 1px ${accent}22 inset, 0 14px 30px -18px ${accent}80` : 'none',
              color: t.text,
            }}>
      {on && (
        <div className="absolute -top-12 -right-10 h-32 w-32 rounded-full blur-2xl opacity-50"
             style={{ background: `radial-gradient(circle, ${accent}, transparent 65%)` }} />
      )}
      <div className="relative flex items-center justify-between">
        <div className="h-10 w-10 rounded-xl grid place-items-center"
             style={{ background: on ? `${accent}22` : (t.mode === 'dark' ? 'rgba(255,255,255,0.05)' : 'rgba(0,0,0,0.04)'),
                      border: `1px solid ${on ? accent + '44' : t.glassBorder}` }}>
          <DomainIcon name={entity.domain} size={20} color={on ? accent : t.textSubtle} />
        </div>
        {on && (
          <span className="text-[10px] uppercase tracking-[0.15em] px-2 py-1 rounded-full"
                style={{ color: accent, background: `${accent}14`, border: `1px solid ${accent}33` }}>live</span>
        )}
      </div>
      <div className="relative mt-4">
        <div className="text-[14.5px] font-semibold tracking-tight">{entity.name}</div>
        <div className="text-[12px] mt-0.5" style={{ color: t.textSubtle }}>{stateLabel(entity, tr)}</div>
      </div>
      {entity.domain === 'light' && on && entity.brightness != null && (
        <div className="relative mt-3 h-[3px] rounded-full overflow-hidden"
             style={{ background: t.mode === 'dark' ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.06)' }}>
          <div className="h-full rounded-full"
               style={{ width: `${(entity.brightness / 255) * 100}%`,
                        background: `linear-gradient(90deg, ${accent}66, ${accent})` }} />
        </div>
      )}
    </button>
  );
}

function stateLabel(e: Entity, tr: ReturnType<typeof useI18n>['t']): string {
  if (e.domain === 'light' && e.isOn && e.brightness != null) {
    return `${Math.round((e.brightness / 255) * 100)}%`;
  }
  if (e.domain === 'climate' && e.temperature != null) {
    return `${e.state} · ${e.temperature.toFixed(1)}°`;
  }
  if (e.domain === 'media_player' && e.mediaTitle) {
    return e.mediaTitle;
  }
  if (e.unit) return `${e.state} ${e.unit}`;
  return e.state.replaceAll('_', ' ');
}

/* ---------- Activity strip (compact bar that links to full page) ---------- */
export function ActivityStrip() {
  const { activity } = useStore();
  const { t: tr } = useI18n();
  const t = useTokens();
  return (
    <Link href="/aurora/activity"
          className="mt-10 block rounded-2xl px-4 py-3"
          style={{ background: t.glass, border: `1px solid ${t.glassBorder}` }}>
      <div className="flex items-center justify-between">
        <div className="text-[10px] uppercase tracking-[0.2em]" style={{ color: t.textFaint }}>
          {tr('activity.title')}
        </div>
        <div className="text-[11px]" style={{ color: t.textFaint }}>
          {tr('activity.lastMin', { n: activity.length })}
        </div>
      </div>
      <div className="mt-3 flex items-center gap-1.5">
        {activity.slice(0, 14).map((ev, i) => {
          const c = accentOf(ev.domain);
          return (
            <div key={ev.id} className="h-2 rounded-full"
                 style={{
                   width: `${24 - i * 1}px`,
                   background: c,
                   opacity: 1 - i * 0.05,
                   boxShadow: i < 3 ? `0 0 10px ${c}` : 'none',
                 }} />
          );
        })}
        {activity.length === 0 && (
          <div className="text-[11px]" style={{ color: t.textFaint }}>{tr('activity.empty')}</div>
        )}
      </div>
      <div className="mt-2 text-[12px] truncate" style={{ color: t.textSubtle }}>
        {activity[0]
          ? `${activity[0].entityName} · ${activity[0].message}`
          : tr('activity.allQuiet')}
      </div>
    </Link>
  );
}

/* ---------- Entity sheet (per-domain controls) ----------
   Opens on tile click. Mutates the store and logs activity. */
export function EntitySheet({ entityId, onClose }:
                            { entityId: string | null; onClose: () => void }) {
  const { entities } = useStore();
  if (!entityId) return null;
  const entity = entities[entityId];
  if (!entity) return null;
  return <EntitySheetBody entity={entity} onClose={onClose} />;
}

function EntitySheetBody({ entity, onClose }: { entity: Entity; onClose: () => void }) {
  const t = useTokens();
  const { t: tr } = useI18n();
  const store = useStore();
  return (
    <div className="fixed inset-0 z-50 grid place-items-end sm:place-items-center"
         onClick={onClose}>
      <div className="absolute inset-0" style={{ background: 'rgba(0,0,0,0.55)', backdropFilter: 'blur(6px)' }} />
      <div className="relative w-full sm:max-w-md rounded-t-3xl sm:rounded-3xl p-6 m-0 sm:m-4"
           onClick={(e) => e.stopPropagation()}
           style={{ background: t.mode === 'dark' ? '#0F1238' : '#FFFFFF',
                    border: `1px solid ${t.glassBorder}`, color: t.text,
                    maxHeight: '90vh', overflow: 'auto' }}>
        <SheetHeader entity={entity} onClose={onClose} />
        <div className="mt-5 space-y-5">{controlsFor(entity, store, tr, t.text, t.textSubtle)}</div>
      </div>
    </div>
  );
}

function SheetHeader({ entity, onClose }: { entity: Entity; onClose: () => void }) {
  const t = useTokens();
  const accent = accentOf(entity.domain);
  return (
    <div className="flex items-center gap-3">
      <div className="h-12 w-12 rounded-2xl grid place-items-center"
           style={{ background: entity.isOn ? `${accent}22` : 'rgba(255,255,255,0.06)',
                    border: `1px solid ${entity.isOn ? accent + '44' : t.glassBorder}` }}>
        <DomainIcon name={entity.domain} size={22} color={entity.isOn ? accent : t.textSubtle} />
      </div>
      <div className="flex-1 min-w-0">
        <div className="text-[17px] font-semibold tracking-tight truncate">{entity.name}</div>
        <div className="text-[12px] truncate" style={{ color: t.textSubtle }}>{entity.id}</div>
      </div>
      <button onClick={onClose} className="rounded-lg p-2 hover:bg-white/5"
              style={{ color: t.textSubtle }} aria-label="Close">
        <DomainIcon name="close" size={18} />
      </button>
    </div>
  );
}

function controlsFor(e: Entity, s: ReturnType<typeof useStore>,
                     tr: ReturnType<typeof useI18n>['t'],
                     textColor: string, subtle: string): React.ReactNode {
  switch (e.domain) {
    case 'light':
      return <>
        <ToggleRow isOn={e.isOn} onChange={() => s.toggle(e.id)} label={tr('sheet.on')} />
        {e.isOn && (
          <SliderRow label={tr('sheet.brightness')}
                     value={e.brightness ?? 0} min={0} max={255}
                     onCommit={(v) => s.setBrightness(e.id, Math.round(v))}
                     display={(v) => `${Math.round((v / 255) * 100)}%`} />
        )}
      </>;

    case 'switch': case 'fan':
      return <>
        <ToggleRow isOn={e.isOn} onChange={() => s.toggle(e.id)} label={tr('sheet.on')} />
      </>;

    case 'cover':
      return <>
        <div className="grid grid-cols-3 gap-3">
          <ActionBtn icon="chevronUp" label={tr('sheet.open')} onClick={() => s.coverCommand(e.id, 'open')} />
          <ActionBtn icon="pause" label={tr('sheet.stop')} onClick={() => s.coverCommand(e.id, 'stop')} />
          <ActionBtn icon="chevronDown" label={tr('sheet.close')} onClick={() => s.coverCommand(e.id, 'close')} />
        </div>
        {e.position != null && (
          <SliderRow label={tr('sheet.position')}
                     value={e.position} min={0} max={100}
                     onCommit={(v) => s.setPosition(e.id, Math.round(v))}
                     display={(v) => `${Math.round(v)}%`} />
        )}
      </>;

    case 'lock':
      return (
        <div className="grid grid-cols-2 gap-3">
          <ActionBtn icon="lock" label={tr('sheet.lock')} onClick={() => s.lockCommand(e.id, 'lock')} />
          <ActionBtn icon="bulb" label={tr('sheet.unlock')} onClick={() => s.lockCommand(e.id, 'unlock')} />
        </div>
      );

    case 'alarm_control_panel':
      return <>
        <CodeField textColor={textColor} subtle={subtle} placeholder={tr('sheet.code')} />
        <div className="grid grid-cols-2 gap-3">
          <ActionBtn icon="check" label={tr('sheet.disarm')} onClick={() => s.alarmCommand(e.id, 'disarm')} />
          <ActionBtn icon="shield" label={tr('sheet.armHome')} onClick={() => s.alarmCommand(e.id, 'arm_home')} />
          <ActionBtn icon="shield" label={tr('sheet.armAway')} onClick={() => s.alarmCommand(e.id, 'arm_away')} />
          <ActionBtn icon="moon" label={tr('sheet.armNight')} onClick={() => s.alarmCommand(e.id, 'arm_night')} />
        </div>
      </>;

    case 'climate':
      return <>
        <TemperatureStepper value={e.temperature ?? 20}
                            onChange={(v) => s.setTemperature(e.id, v)}
                            min={5} max={32} step={0.5} />
        <ModeChips modes={['heat', 'cool', 'auto', 'dry', 'fan_only', 'off']}
                   current={e.hvacMode ?? e.state}
                   onPick={(m) => s.setHvacMode(e.id, m)} tr={tr} />
      </>;

    case 'media_player':
      return <>
        {e.mediaTitle && (
          <div className="text-center text-[14px]"
               style={{ color: textColor, opacity: 0.9 }}>{tr('sheet.nowPlaying')}: {e.mediaTitle}</div>
        )}
        <div className="grid grid-cols-3 gap-3">
          <ActionBtn icon="skipBack" label={tr('sheet.prev')} onClick={() => s.mediaCommand(e.id, 'prev')} />
          <ActionBtn icon={e.state === 'playing' ? 'pause' : 'play'}
                     label={e.state === 'playing' ? tr('sheet.pause') : tr('sheet.play')}
                     onClick={() => s.mediaCommand(e.id, 'play_pause')} />
          <ActionBtn icon="skipFwd" label={tr('sheet.next')} onClick={() => s.mediaCommand(e.id, 'next')} />
        </div>
        {e.volume != null && (
          <SliderRow label={tr('sheet.volume')}
                     value={e.volume * 100} min={0} max={100}
                     onCommit={(v) => s.setVolume(e.id, v / 100)}
                     display={(v) => `${Math.round(v)}%`} />
        )}
      </>;

    case 'vacuum':
      return (
        <div className="grid grid-cols-3 gap-3">
          <ActionBtn icon="play" label={tr('sheet.startCleaning')} onClick={() => s.vacuumCommand(e.id, 'start')} />
          <ActionBtn icon="pause" label={tr('sheet.pauseClean')} onClick={() => s.vacuumCommand(e.id, 'pause')} />
          <ActionBtn icon="hub" label={tr('sheet.returnDock')} onClick={() => s.vacuumCommand(e.id, 'return_to_base')} />
        </div>
      );

    case 'scene': case 'script':
      return (
        <div>
          <ActionBtn icon="play" label={tr('sheet.activate')} onClick={() => s.activate(e.id)} fullWidth />
        </div>
      );

    /* sensor / binary_sensor / camera / unknown: read-only attributes */
    default:
      return (
        <div>
          <div className="text-[12px] uppercase tracking-[0.18em] mb-2" style={{ color: subtle }}>{tr('sheet.attributes')}</div>
          <div className="space-y-1 text-[13px]">
            <KV label="state" value={e.state} />
            {e.unit && <KV label="unit" value={e.unit} />}
            <KV label="entity_id" value={e.id} />
            <KV label="domain" value={e.domain} />
            <KV label="area" value={e.area} />
          </div>
        </div>
      );
  }
}

function KV({ label, value }: { label: string; value: string }) {
  const t = useTokens();
  return (
    <div className="flex items-baseline gap-3">
      <div className="w-24 text-[11px] uppercase tracking-[0.15em]" style={{ color: t.textFaint }}>{label}</div>
      <div className="flex-1">{value}</div>
    </div>
  );
}

function ToggleRow({ isOn, onChange, label }: { isOn: boolean; onChange: () => void; label: string }) {
  const t = useTokens();
  return (
    <button onClick={onChange}
            className="w-full flex items-center justify-between px-4 py-3 rounded-2xl transition-colors"
            style={{ background: t.glass, border: `1px solid ${t.glassBorder}`, color: t.text }}>
      <span className="text-[14px] font-medium">{label}</span>
      <span className="relative h-7 w-12 rounded-full transition-colors"
            style={{ background: isOn ? '#34D399' : 'rgba(255,255,255,0.15)' }}>
        <span className="absolute top-0.5 h-6 w-6 rounded-full bg-white transition-all"
              style={{ left: isOn ? 22 : 2 }} />
      </span>
    </button>
  );
}

function SliderRow({ label, value, min, max, onCommit, display }:
                   { label: string; value: number; min: number; max: number;
                     onCommit: (v: number) => void; display: (v: number) => string }) {
  const t = useTokens();
  const [drag, setDrag] = React.useState<number | null>(null);
  const v = drag ?? value;
  return (
    <div>
      <div className="flex items-baseline justify-between text-[12px] mb-1" style={{ color: t.textSubtle }}>
        <span>{label}</span>
        <span style={{ color: t.text }}>{display(v)}</span>
      </div>
      <input type="range" min={min} max={max} value={v}
             onChange={(e) => setDrag(Number(e.target.value))}
             onMouseUp={(e) => { onCommit(Number((e.target as HTMLInputElement).value)); setDrag(null); }}
             onTouchEnd={(e) => { onCommit(Number((e.target as HTMLInputElement).value)); setDrag(null); }}
             className="w-full accent-teal-400" />
    </div>
  );
}

function TemperatureStepper({ value, onChange, min, max, step }:
                             { value: number; onChange: (v: number) => void;
                               min: number; max: number; step: number }) {
  const t = useTokens();
  return (
    <div className="flex items-center justify-center gap-5">
      <button onClick={() => value - step >= min && onChange(+(value - step).toFixed(1))}
              className="h-12 w-12 rounded-full grid place-items-center"
              style={{ background: t.glass, border: `1px solid ${t.glassBorder}`, color: t.text }}>
        <DomainIcon name="minus" size={18} />
      </button>
      <div className="text-[40px] font-semibold tabular-nums"
           style={{ fontFamily: '"Space Grotesk", Inter, sans-serif' }}>
        {value.toFixed(1)}°
      </div>
      <button onClick={() => value + step <= max && onChange(+(value + step).toFixed(1))}
              className="h-12 w-12 rounded-full grid place-items-center"
              style={{ background: t.glass, border: `1px solid ${t.glassBorder}`, color: t.text }}>
        <DomainIcon name="plus" size={18} />
      </button>
    </div>
  );
}

function ModeChips({ modes, current, onPick, tr }:
                   { modes: string[]; current: string; onPick: (m: string) => void;
                     tr: ReturnType<typeof useI18n>['t'] }) {
  const t = useTokens();
  const label = (m: string) => {
    switch (m) {
      case 'heat': return tr('sheet.heat');
      case 'cool': return tr('sheet.cool');
      case 'auto': return tr('sheet.auto');
      case 'dry': return tr('sheet.dry');
      case 'fan_only': return tr('sheet.fan');
      case 'off': return tr('sheet.off');
      default: return m;
    }
  };
  return (
    <div>
      <div className="text-[11px] uppercase tracking-[0.18em] mb-2" style={{ color: t.textFaint }}>{tr('sheet.modes')}</div>
      <div className="flex flex-wrap gap-2">
        {modes.map(m => (
          <button key={m} onClick={() => onPick(m)}
                  className="px-3 py-1.5 rounded-full text-[12px] transition-colors"
                  style={{
                    background: current === m ? '#5EEAD4' : t.glass,
                    color: current === m ? '#0F172A' : t.text,
                    border: `1px solid ${current === m ? '#5EEAD4' : t.glassBorder}`,
                  }}>
            {label(m)}
          </button>
        ))}
      </div>
    </div>
  );
}

function ActionBtn({ icon, label, onClick, fullWidth }:
                   { icon: string; label: string; onClick: () => void; fullWidth?: boolean }) {
  const t = useTokens();
  return (
    <button onClick={onClick}
            className={`flex ${fullWidth ? 'w-full justify-center' : 'flex-col items-center'} gap-1.5 px-4 py-3 rounded-2xl transition-all hover:-translate-y-0.5 active:scale-95`}
            style={{ background: t.glass, border: `1px solid ${t.glassBorder}`, color: t.text }}>
      <DomainIcon name={icon} size={20} />
      <span className="text-[11.5px]">{label}</span>
    </button>
  );
}

function CodeField({ textColor, subtle, placeholder }:
                   { textColor: string; subtle: string; placeholder: string }) {
  const [v, setV] = React.useState('');
  const t = useTokens();
  return (
    <input value={v} onChange={(e) => setV(e.target.value)} type="password"
           placeholder={placeholder}
           className="w-full px-4 py-3 rounded-2xl outline-none"
           style={{ background: t.glass, border: `1px solid ${t.glassBorder}`,
                    color: textColor, fontSize: 14 }} />
  );
}

/* ---------- Hook: group entities into areas ---------- */
export function useGrouped() {
  const { entities } = useStore();
  return React.useMemo(() => {
    const out: Record<AreaKey, Entity[]> = {
      living_room: [], kitchen: [], bedroom: [], entryway: [], outside: [],
    };
    for (const e of Object.values(entities)) {
      if (isAreaKey(e.area)) out[e.area].push(e);
    }
    return out;
  }, [entities]);
}
