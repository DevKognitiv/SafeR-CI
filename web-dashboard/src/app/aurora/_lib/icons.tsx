import * as React from 'react';

/* Single-source-of-truth SVG paths for every domain (Lucide-shaped). */
const PATHS: Record<string, React.ReactNode> = {
  light: <path d="M9 18h6M10 22h4M12 2a7 7 0 0 0-4 12.7c.9.7 1.4 1.7 1.4 2.8V18h5.2v-.5c0-1.1.5-2.1 1.4-2.8A7 7 0 0 0 12 2z" />,
  switch: <><circle cx="12" cy="12" r="10" /><path d="M8 12h8M12 8v8" /></>,
  fan: <><circle cx="12" cy="12" r="2" /><path d="M12 2v4M22 12h-4M12 22v-4M2 12h4M16 8a4 4 0 0 0-4-4M20 16a4 4 0 0 0-4-4M8 16a4 4 0 0 0 4 4M4 8a4 4 0 0 0 4 4" /></>,
  cover: <><rect x="4" y="4" width="16" height="4" /><path d="M4 8v12M20 8v12M4 14h16M4 20h16" /></>,
  climate: <path d="M14 14.76V3.5a2.5 2.5 0 0 0-5 0v11.26a4.5 4.5 0 1 0 5 0z" />,
  media_player: <><path d="M9 18V5l12-2v13" /><circle cx="6" cy="18" r="3" /><circle cx="18" cy="16" r="3" /></>,
  lock: <><rect x="3" y="11" width="18" height="11" rx="2" /><path d="M7 11V7a5 5 0 0 1 10 0v4" /></>,
  alarm_control_panel: <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />,
  camera: <><path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z" /><circle cx="12" cy="13" r="4" /></>,
  sensor: <path d="M3 12h4l3-9 4 18 3-9h4" />,
  binary_sensor: <><rect x="3" y="6" width="18" height="12" rx="6" /><circle cx="15" cy="12" r="3" /></>,
  vacuum: <><circle cx="12" cy="12" r="9" /><circle cx="12" cy="12" r="3" /></>,
  scene: <><circle cx="13.5" cy="6.5" r="2.5" /><circle cx="19" cy="13" r="2.5" /><circle cx="6" cy="12" r="2.5" /><circle cx="10" cy="19" r="2.5" /></>,
  script: <path d="M5 8l4 4-4 4M13 16h6" />,
  thermometer: <path d="M14 14.76V3.5a2.5 2.5 0 0 0-5 0v11.26a4.5 4.5 0 1 0 5 0z" />,
  droplet: <path d="M12 3.5l5 7.4a6 6 0 1 1-10 0z" />,
  shield: <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />,
  user: <><circle cx="12" cy="7" r="4" /><path d="M16 21v-2a4 4 0 0 0-8 0v2" /></>,
  bulb: <path d="M9 18h6M10 22h4M12 2a7 7 0 0 0-4 12.7c.9.7 1.4 1.7 1.4 2.8V18h5.2v-.5c0-1.1.5-2.1 1.4-2.8A7 7 0 0 0 12 2z" />,
  thermostat: <path d="M14 14.76V3.5a2.5 2.5 0 0 0-5 0v11.26a4.5 4.5 0 1 0 5 0z" />,
  plug: <path d="M9 2v6M15 2v6M7 8h10v4a5 5 0 0 1-10 0zM12 17v5" />,
  speaker: <><rect x="6" y="3" width="12" height="18" rx="2" /><circle cx="12" cy="14" r="3" /><circle cx="12" cy="7" r="1" /></>,
  hub: <><circle cx="12" cy="12" r="2" /><path d="M4 12a8 8 0 0 1 8-8M20 12a8 8 0 0 1-8 8M9 12a3 3 0 0 1 3-3" /></>,
  panel: <><rect x="3" y="4" width="18" height="14" rx="2" /><path d="M7 9h4M7 13h4M15 9h2M15 13h2" /></>,
  cog: <><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3h.1a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8v.1a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z" /></>,
  arrowLeft: <path d="M19 12H5M12 19l-7-7 7-7" />,
  arrowRight: <path d="M5 12h14M12 5l7 7-7 7" />,
  menu: <path d="M3 6h18M3 12h18M3 18h18" />,
  close: <path d="M18 6L6 18M6 6l12 12" />,
  check: <path d="M5 12l5 5L20 7" />,
  play: <path d="M5 4l14 8-14 8z" />,
  pause: <><rect x="6" y="4" width="4" height="16" /><rect x="14" y="4" width="4" height="16" /></>,
  skipFwd: <><path d="M5 4l10 8-10 8z" /><line x1="19" y1="5" x2="19" y2="19" /></>,
  skipBack: <><path d="M19 20L9 12l10-8z" /><line x1="5" y1="19" x2="5" y2="5" /></>,
  chevronUp: <path d="M18 15l-6-6-6 6" />,
  chevronDown: <path d="M6 9l6 6 6-6" />,
  chevronRight: <path d="M9 18l6-6-6-6" />,
  minus: <path d="M5 12h14" />,
  plus: <path d="M12 5v14M5 12h14" />,
  refresh: <path d="M21 12a9 9 0 0 1-15 6.7L3 16M3 12a9 9 0 0 1 15-6.7L21 8M21 3v5h-5M3 21v-5h5" />,
  sun: <><circle cx="12" cy="12" r="5" /><path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.93 4.93l2.12 2.12M16.95 16.95l2.12 2.12M4.93 19.07l2.12-2.12M16.95 7.05l2.12-2.12" /></>,
  moon: <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />,
  cloud: <path d="M17 21H7a5 5 0 0 1 0-10 7 7 0 0 1 13.5 1A4 4 0 0 1 17 21z" />,
  cloudRain: <><path d="M17 17H7a5 5 0 0 1 0-10 7 7 0 0 1 13.5 1A4 4 0 0 1 17 17z" /><line x1="8" y1="20" x2="8" y2="22" /><line x1="12" y1="20" x2="12" y2="22" /><line x1="16" y1="20" x2="16" y2="22" /></>,
  cloudSnow: <><path d="M17 17H7a5 5 0 0 1 0-10 7 7 0 0 1 13.5 1A4 4 0 0 1 17 17z" /><line x1="8" y1="21" x2="8" y2="21" /><line x1="12" y1="21" x2="12" y2="21" /><line x1="16" y1="21" x2="16" y2="21" /></>,
  cloudFog: <><path d="M17 16H7a5 5 0 0 1 0-10 7 7 0 0 1 13.5 1A4 4 0 0 1 17 16z" /><line x1="5" y1="20" x2="19" y2="20" /><line x1="3" y1="22" x2="21" y2="22" /></>,
  storm: <><path d="M19 16.9A5 5 0 0 0 18 7h-1.26A8 8 0 1 0 4 15.25" /><path d="M13 11l-4 6h6l-4 6" /></>,
};

export function DomainIcon({ name, size = 20, color, strokeWidth = 1.8 }:
                           { name: string; size?: number; color?: string; strokeWidth?: number }) {
  const path = PATHS[name] ?? PATHS.script;
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none"
         stroke={color ?? 'currentColor'} strokeWidth={strokeWidth}
         strokeLinecap="round" strokeLinejoin="round">{path}</svg>
  );
}

/* SafeR S logo, used by the watermark background. */
export function SafeRLogo({ size = 80, color = 'currentColor' }:
                          { size?: number; color?: string }) {
  return (
    <svg width={size} height={size * 1.05} viewBox="0 0 100 105" fill="none">
      <defs>
        <linearGradient id="safer-g" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#14B8A6" />
          <stop offset="100%" stopColor="#818CF8" />
        </linearGradient>
      </defs>
      <path d="M50 6 L88 22 V52 C88 76 70 95 50 100 C30 95 12 76 12 52 V22 Z"
            fill="none" stroke={color} strokeWidth="3" />
      <path d="M62 38 Q56 30 46 32 Q36 34 38 44 Q40 52 50 53 Q60 54 62 62 Q64 72 54 74 Q44 76 38 68"
            fill="none" stroke={color} strokeWidth="4" strokeLinecap="round" />
    </svg>
  );
}

/* A single product card used in the 100-item slideshow.
   Pure SVG so there's nothing to fetch. */
export function ProductCard({ device, accent, hue, size = 180 }:
                            { device: string; accent: string; hue: string; size?: number }) {
  const inner = (() => {
    switch (device) {
      case 'bulb': return <DomainIcon name="bulb" size={size * 0.4} color="#FFF" strokeWidth={2.2} />;
      case 'lock': return <DomainIcon name="lock" size={size * 0.4} color="#FFF" strokeWidth={2.2} />;
      case 'thermostat': return <DomainIcon name="thermostat" size={size * 0.4} color="#FFF" strokeWidth={2.2} />;
      case 'camera': return <DomainIcon name="camera" size={size * 0.42} color="#FFF" strokeWidth={2} />;
      case 'sensor': return <DomainIcon name="sensor" size={size * 0.42} color="#FFF" strokeWidth={2.4} />;
      case 'plug': return <DomainIcon name="plug" size={size * 0.4} color="#FFF" strokeWidth={2.2} />;
      case 'speaker': return <DomainIcon name="speaker" size={size * 0.4} color="#FFF" strokeWidth={2.2} />;
      case 'hub': return <DomainIcon name="hub" size={size * 0.42} color="#FFF" strokeWidth={2.2} />;
      case 'fan': return <DomainIcon name="fan" size={size * 0.42} color="#FFF" strokeWidth={2.2} />;
      case 'cover': return <DomainIcon name="cover" size={size * 0.4} color="#FFF" strokeWidth={2.2} />;
      case 'vacuum': return <DomainIcon name="vacuum" size={size * 0.42} color="#FFF" strokeWidth={2.2} />;
      case 'panel': return <DomainIcon name="panel" size={size * 0.42} color="#FFF" strokeWidth={2.2} />;
      default: return null;
    }
  })();
  return (
    <div style={{
      width: size, height: size,
      borderRadius: size * 0.18,
      background: `linear-gradient(135deg, ${accent} 0%, ${hue} 100%)`,
      display: 'grid', placeItems: 'center',
      boxShadow: `0 18px 36px -16px ${accent}99, inset 0 1px 0 rgba(255,255,255,0.18)`,
    }}>
      {inner}
    </div>
  );
}
