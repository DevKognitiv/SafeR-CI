'use client';

import * as React from 'react';
import Link from 'next/link';
import { useI18n, useSettings, useTokens } from './providers';
import { DomainIcon, ProductCard, SafeRLogo } from './icons';
import { buildSlides } from './data';

/* ---------- Aurora shell wraps every page with gradient + washes + background ---------- */
export function AuroraShell({ children }: { children: React.ReactNode }) {
  const t = useTokens();
  const { background } = useSettings();
  return (
    <div
      className="min-h-screen relative overflow-hidden"
      style={{
        color: t.text,
        background: t.background,
        fontFamily: 'Inter, system-ui, sans-serif',
      }}>
      {/* Aurora washes */}
      <Wash color={t.washes[0]} className="-top-32 -right-24 h-[520px] w-[520px] opacity-50" />
      <Wash color={t.washes[1]} className="-bottom-40 -left-24 h-[560px] w-[560px] opacity-40" />
      <Wash color={t.washes[2]} className="top-1/3 left-1/2 -translate-x-1/2 h-[420px] w-[420px] opacity-25" />

      {/* Background layer (watermark / slideshow / none) */}
      {background === 'watermark' && <WatermarkBg color={t.text} />}
      {background === 'slideshow' && <SlideshowBg />}

      <main className="relative max-w-6xl mx-auto px-6 pt-8 pb-16">{children}</main>
    </div>
  );
}

function Wash({ color, className }: { color: string; className: string }) {
  return (
    <div className={`pointer-events-none absolute rounded-full blur-3xl ${className}`}
         style={{ background: `radial-gradient(circle, ${color} 0%, transparent 60%)` }} />
  );
}

/* SafeR logo watermark at 10% opacity. Single large center logo for the
   hero, plus a quiet repeating field on big screens. */
function WatermarkBg({ color }: { color: string }) {
  return (
    <div className="pointer-events-none absolute inset-0 grid place-items-center" style={{ opacity: 0.10 }}>
      <SafeRLogo size={420} color={color} />
    </div>
  );
}

/* 100-card slideshow. Cards cycle through in groups of 6 with crossfade. */
function SlideshowBg() {
  const slides = React.useMemo(() => buildSlides(), []);
  const [page, setPage] = React.useState(0);
  React.useEffect(() => {
    const pages = Math.ceil(slides.length / 6);
    const id = setInterval(() => setPage(p => (p + 1) % pages), 5000);
    return () => clearInterval(id);
  }, [slides.length]);
  const visible = slides.slice(page * 6, page * 6 + 6);
  return (
    <div className="pointer-events-none absolute inset-0 overflow-hidden">
      <div className="absolute inset-0 grid grid-cols-3 gap-10 p-10 opacity-[0.18] transition-opacity duration-1000"
           key={page} style={{ filter: 'blur(0.5px)' }}>
        {visible.map((s, i) => (
          <div key={s.key} className="flex items-center justify-center"
               style={{ transform: `translateY(${(i % 2 === 0 ? -10 : 10)}px) rotate(${(i % 2 === 0 ? -3 : 3)}deg)` }}>
            <ProductCard device={s.device} accent={s.accent} hue={s.hue} size={180} />
          </div>
        ))}
      </div>
      {/* Vignette so cards read as background, not content */}
      <div className="absolute inset-0"
           style={{ background: 'radial-gradient(ellipse at center, transparent 0%, rgba(0,0,0,0.55) 80%)' }} />
    </div>
  );
}

/* ---------- Top bar ---------- */
export function TopBar({ back }: { back?: { href: string; label: string } }) {
  const t = useTokens();
  const { t: tr } = useI18n();
  return (
    <header className="flex items-center justify-between gap-4">
      <div className="flex items-center gap-3 min-w-0">
        {back ? (
          <Link href={back.href} className="rounded-lg p-2 -ml-2 hover:bg-white/5 transition-colors"
                aria-label={back.label} style={{ color: t.textSubtle }}>
            <DomainIcon name="arrowLeft" size={20} />
          </Link>
        ) : (
          <button className="rounded-lg p-2 -ml-2 hover:bg-white/5 transition-colors"
                  aria-label={tr('top.menu')} style={{ color: t.textSubtle }}>
            <DomainIcon name="menu" size={20} />
          </button>
        )}
        <div className="h-9 w-9 rounded-xl grid place-items-center border"
             style={{ background: 'linear-gradient(135deg, #14B8A6, #818CF8)', borderColor: t.glassBorder }}>
          <span className="text-[15px] font-semibold text-white">S</span>
        </div>
        <div className="min-w-0">
          <div className="text-[15px] font-semibold tracking-tight truncate">SafeR Home</div>
          <div className="text-[11px] uppercase tracking-[0.18em] truncate"
               style={{ color: t.textFaint }}>{tr('app.tagline')}</div>
        </div>
      </div>
      <div className="flex items-center gap-1">
        <span className="hidden sm:inline-flex items-center gap-2 text-[12px] mr-2" style={{ color: t.textSubtle }}>
          <span className="relative inline-flex h-2 w-2">
            <span className="absolute inline-flex h-full w-full rounded-full opacity-60 animate-ping"
                  style={{ background: '#34D399' }} />
            <span className="relative inline-flex rounded-full h-2 w-2" style={{ background: '#34D399' }} />
          </span>
          {tr('top.connected')}
        </span>
        <Link href="/aurora/settings" className="rounded-lg p-2 hover:bg-white/5 transition-colors"
              aria-label={tr('top.settings')} style={{ color: t.textSubtle }}>
          <DomainIcon name="cog" size={20} />
        </Link>
      </div>
    </header>
  );
}

/* ---------- Glass card primitive ---------- */
export function GlassCard({ children, className = '', style = {} }:
                          { children: React.ReactNode; className?: string; style?: React.CSSProperties }) {
  const t = useTokens();
  return (
    <div className={`rounded-[22px] ${className}`}
         style={{
           background: t.glass,
           border: `1px solid ${t.glassBorder}`,
           backdropFilter: 'blur(14px)',
           WebkitBackdropFilter: 'blur(14px)',
           ...style,
         }}>{children}</div>
  );
}

/* ---------- Bottom nav (links between sub-pages) ---------- */
export function BottomNav({ current }: { current: 'dashboard' | 'activity' | 'settings' }) {
  const t = useTokens();
  const { t: tr } = useI18n();
  const items: { key: typeof current; href: string; icon: string }[] = [
    { key: 'dashboard', href: '/aurora', icon: 'hub' },
    { key: 'activity', href: '/aurora/activity', icon: 'sensor' },
    { key: 'settings', href: '/aurora/settings', icon: 'cog' },
  ];
  return (
    <div className="mt-12">
      <GlassCard className="px-2 py-1.5 flex items-center justify-around">
        {items.map(it => (
          <Link key={it.key} href={it.href}
                className="flex flex-col items-center gap-0.5 px-4 py-1.5 rounded-xl transition-colors"
                style={{
                  background: it.key === current ? 'rgba(20,184,166,0.18)' : 'transparent',
                  color: it.key === current ? '#5EEAD4' : t.textSubtle,
                }}>
            <DomainIcon name={it.icon} size={18} />
            <span className="text-[10.5px] uppercase tracking-[0.12em]">
              {tr(`nav.${it.key}` as `nav.${typeof current}`)}
            </span>
          </Link>
        ))}
      </GlassCard>
    </div>
  );
}
