'use client';

import { AuroraShell, BottomNav, GlassCard, TopBar } from '../_lib/shell';
import { useI18n, useSettings, useTokens } from '../_lib/providers';
import { LOCALE_LABELS, type BackgroundChoice, type Locale, type ThemeChoice } from '../_lib/data';
import { DomainIcon } from '../_lib/icons';

export default function AuroraSettingsPage() {
  const { t: tr } = useI18n();
  return (
    <AuroraShell>
      <TopBar back={{ href: '/aurora', label: tr('activity.back') }} />
      <h1 className="mt-7 text-[28px] font-semibold tracking-tight"
          style={{ fontFamily: '"Space Grotesk", Inter, sans-serif' }}>
        {tr('settings.title')}
      </h1>

      <div className="mt-6 grid gap-5">
        <ThemeSection />
        <LanguageSection />
        <BackgroundSection />
        <ConnectionSection />
        <AboutSection />
      </div>

      <BottomNav current="settings" />
    </AuroraShell>
  );
}

function Section({ title, hint, children }:
                 { title: string; hint?: string; children: React.ReactNode }) {
  const t = useTokens();
  return (
    <GlassCard className="p-5">
      <div className="flex items-baseline justify-between">
        <h2 className="text-[12px] uppercase tracking-[0.18em]" style={{ color: t.textFaint }}>{title}</h2>
        {hint && <span className="text-[11px]" style={{ color: t.textFaint }}>{hint}</span>}
      </div>
      <div className="mt-3">{children}</div>
    </GlassCard>
  );
}

function ThemeSection() {
  const { t: tr } = useI18n();
  const { theme, setTheme, weather } = useSettings();
  const t = useTokens();
  const choices: { key: ThemeChoice; label: string; icon: string }[] = [
    { key: 'dark', label: tr('settings.theme.dark'), icon: 'moon' },
    { key: 'light', label: tr('settings.theme.light'), icon: 'sun' },
    { key: 'dynamic', label: tr('settings.theme.dynamic'), icon: 'cloud' },
  ];
  const variant = t.variant ?? '';
  const [tod, wx] = variant.split('·');
  return (
    <Section title={tr('settings.theme')}>
      <div className="grid grid-cols-3 gap-3">
        {choices.map(c => (
          <button key={c.key} onClick={() => setTheme(c.key)}
                  className="rounded-2xl p-4 text-left transition-all hover:-translate-y-0.5"
                  style={{
                    background: theme === c.key
                      ? 'linear-gradient(135deg, #14B8A6, #818CF8)'
                      : 'rgba(255,255,255,0.04)',
                    color: theme === c.key ? '#0F172A' : t.text,
                    border: `1px solid ${theme === c.key ? 'transparent' : t.glassBorder}`,
                  }}>
            <div className="flex items-center justify-between">
              <DomainIcon name={c.icon} size={20} />
              {theme === c.key && <DomainIcon name="check" size={16} />}
            </div>
            <div className="mt-3 text-[15px] font-semibold">{c.label}</div>
            {c.key === 'dynamic' && (
              <div className="text-[11px] mt-1"
                   style={{ color: theme === c.key ? 'rgba(15,23,42,0.7)' : t.textSubtle }}>
                {tr('settings.theme.dynamicHint')}
              </div>
            )}
          </button>
        ))}
      </div>
      {theme === 'dynamic' && variant && (
        <div className="mt-3 flex items-center gap-3 px-4 py-2 rounded-full text-[12px]"
             style={{ background: t.glass, border: `1px solid ${t.glassBorder}`, color: t.text, width: 'fit-content' }}>
          <DomainIcon name={
            wx === 'rain' ? 'cloudRain' : wx === 'snow' ? 'cloudSnow' :
            wx === 'storm' ? 'storm' : wx === 'fog' ? 'cloudFog' :
            wx === 'partly' ? 'cloud' : 'sun'
          } size={14} />
          <span style={{ color: t.textSubtle }}>
            {tr(`settings.tod.${tod as 'dawn' | 'day' | 'dusk' | 'night'}`)}
            {' · '}
            {tr(`settings.weather.${wx as 'clear' | 'partly' | 'rain' | 'snow' | 'storm' | 'fog'}`)}
          </span>
        </div>
      )}
    </Section>
  );
}

function LanguageSection() {
  const { t: tr } = useI18n();
  const { locale, setLocale } = useSettings();
  const t = useTokens();
  const langs = Object.entries(LOCALE_LABELS) as [Locale, string][];
  return (
    <Section title={tr('settings.language')}>
      <div className="flex flex-wrap gap-2">
        {langs.map(([key, label]) => (
          <button key={key} onClick={() => setLocale(key)}
                  className="px-4 py-2 rounded-full text-[13px] transition-colors"
                  style={{
                    background: locale === key ? '#5EEAD4' : t.glass,
                    color: locale === key ? '#0F172A' : t.text,
                    border: `1px solid ${locale === key ? '#5EEAD4' : t.glassBorder}`,
                  }}>
            {label}
          </button>
        ))}
      </div>
    </Section>
  );
}

function BackgroundSection() {
  const { t: tr } = useI18n();
  const { background, setBackground } = useSettings();
  const t = useTokens();
  const items: { key: BackgroundChoice; title: string; hint: string }[] = [
    { key: 'watermark', title: tr('settings.bg.watermark'), hint: tr('settings.bg.watermarkHint') },
    { key: 'slideshow', title: tr('settings.bg.slideshow'), hint: tr('settings.bg.slideshowHint') },
    { key: 'none', title: tr('settings.bg.none'), hint: tr('settings.bg.noneHint') },
  ];
  return (
    <Section title={tr('settings.background')}>
      <div className="grid gap-2">
        {items.map(it => (
          <button key={it.key} onClick={() => setBackground(it.key)}
                  className="flex items-center gap-3 px-4 py-3 rounded-2xl text-left transition-colors"
                  style={{
                    background: background === it.key ? 'rgba(94,234,212,0.12)' : t.glass,
                    border: `1px solid ${background === it.key ? '#5EEAD4' : t.glassBorder}`,
                    color: t.text,
                  }}>
            <span className="h-5 w-5 rounded-full grid place-items-center"
                  style={{ background: background === it.key ? '#5EEAD4' : 'transparent',
                           border: `2px solid ${background === it.key ? '#5EEAD4' : t.textFaint}` }}>
              {background === it.key && <DomainIcon name="check" size={12} color="#0F172A" />}
            </span>
            <div>
              <div className="text-[14px] font-semibold">{it.title}</div>
              <div className="text-[12px]" style={{ color: t.textSubtle }}>{it.hint}</div>
            </div>
          </button>
        ))}
      </div>
    </Section>
  );
}

function ConnectionSection() {
  const { t: tr } = useI18n();
  const t = useTokens();
  return (
    <Section title={tr('settings.connection')}>
      <div className="text-[13px]" style={{ color: t.textSubtle }}>{tr('settings.connectionHint')}</div>
    </Section>
  );
}

function AboutSection() {
  const { t: tr } = useI18n();
  const t = useTokens();
  return (
    <Section title={tr('settings.about')}>
      <div className="text-[13px]" style={{ color: t.textSubtle }}>{tr('settings.aboutBody')}</div>
    </Section>
  );
}
