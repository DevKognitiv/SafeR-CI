'use client';

import * as React from 'react';
import {
  ActivityEntry, BackgroundChoice, DICTIONARIES, DictKey, Dictionary,
  Entity, INITIAL_ENTITIES, Locale, ThemeChoice, ThemeTokens,
  DARK_TOKENS, LIGHT_TOKENS, WeatherCondition, resolveDynamicTokens,
  weatherFromCode,
} from './data';

/* ---------- Settings (locale + theme choice + background choice) ---------- */

type Settings = {
  locale: Locale;
  theme: ThemeChoice;
  background: BackgroundChoice;
  weather: WeatherCondition;
  setLocale(l: Locale): void;
  setTheme(t: ThemeChoice): void;
  setBackground(b: BackgroundChoice): void;
};

const SettingsCtx = React.createContext<Settings | null>(null);
export const useSettings = () => {
  const v = React.useContext(SettingsCtx);
  if (!v) throw new Error('useSettings outside SettingsProvider');
  return v;
};

const LS = {
  locale: 'aurora.locale',
  theme: 'aurora.theme',
  background: 'aurora.background',
};

function readLS<T extends string>(key: string, fallback: T, allowed: readonly T[]): T {
  if (typeof window === 'undefined') return fallback;
  const v = window.localStorage.getItem(key);
  return v && (allowed as readonly string[]).includes(v) ? (v as T) : fallback;
}

export function SettingsProvider({ children }: { children: React.ReactNode }) {
  const [locale, setLocaleState] = React.useState<Locale>('fr');
  const [theme, setThemeState] = React.useState<ThemeChoice>('dark');
  const [background, setBackgroundState] =
    React.useState<BackgroundChoice>('watermark');
  const [weather, setWeather] = React.useState<WeatherCondition>('clear');

  /* hydrate from localStorage on mount (avoids hydration mismatch) */
  React.useEffect(() => {
    setLocaleState(readLS<Locale>(LS.locale, 'fr', ['fr','en','es','de','pt']));
    setThemeState(readLS<ThemeChoice>(LS.theme, 'dark', ['dark','light','dynamic']));
    setBackgroundState(readLS<BackgroundChoice>(LS.background, 'watermark', ['watermark','slideshow','none']));
  }, []);

  /* weather fetch (Open-Meteo, no key). Failures fall back to 'clear'. */
  React.useEffect(() => {
    let aborted = false;
    const fetchWeather = (lat: number, lon: number) =>
      fetch(`https://api.open-meteo.com/v1/forecast?latitude=${lat}&longitude=${lon}&current=weather_code`)
        .then(r => r.ok ? r.json() : Promise.reject(r.status))
        .then(j => { if (!aborted) setWeather(weatherFromCode(j?.current?.weather_code)); })
        .catch(() => {});
    if (typeof navigator !== 'undefined' && navigator.geolocation) {
      navigator.geolocation.getCurrentPosition(
        p => fetchWeather(p.coords.latitude, p.coords.longitude),
        () => fetchWeather(5.32, -4.02), // Abidjan fallback
        { timeout: 4000 },
      );
    } else {
      fetchWeather(5.32, -4.02);
    }
    return () => { aborted = true; };
  }, []);

  const setLocale = (l: Locale) => {
    setLocaleState(l);
    if (typeof window !== 'undefined') window.localStorage.setItem(LS.locale, l);
  };
  const setTheme = (t: ThemeChoice) => {
    setThemeState(t);
    if (typeof window !== 'undefined') window.localStorage.setItem(LS.theme, t);
  };
  const setBackground = (b: BackgroundChoice) => {
    setBackgroundState(b);
    if (typeof window !== 'undefined') window.localStorage.setItem(LS.background, b);
  };

  return (
    <SettingsCtx.Provider
      value={{ locale, theme, background, weather, setLocale, setTheme, setBackground }}>
      {children}
    </SettingsCtx.Provider>
  );
}

/* ---------- i18n ---------- */

export function useI18n() {
  const { locale } = useSettings();
  return React.useMemo(() => {
    const d: Dictionary = DICTIONARIES[locale];
    const t = (k: DictKey, vars?: Record<string, string | number>) => {
      let s = d[k] ?? k;
      if (vars) {
        for (const [name, val] of Object.entries(vars)) {
          s = s.replaceAll(`{${name}}`, String(val));
        }
      }
      return s;
    };
    return { t, locale, dict: d };
  }, [locale]);
}

/* ---------- Theme tokens (computed; rebuilds when theme/weather flips) ---------- */

export function useTokens(): ThemeTokens {
  const { theme, weather } = useSettings();
  const [now, setNow] = React.useState<Date>(() => new Date());
  /* re-tick every 5 minutes so dynamic mode crosses dawn/dusk on long sessions */
  React.useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 5 * 60 * 1000);
    return () => clearInterval(id);
  }, []);
  return React.useMemo(() => {
    if (theme === 'dark') return DARK_TOKENS;
    if (theme === 'light') return LIGHT_TOKENS;
    return resolveDynamicTokens(now, weather);
  }, [theme, now, weather]);
}

/* ---------- Entity store + activity log ---------- */

type Store = {
  entities: Record<string, Entity>;
  activity: ActivityEntry[];
  toggle(id: string): void;
  setBrightness(id: string, value: number): void;
  setPosition(id: string, value: number): void;
  coverCommand(id: string, cmd: 'open' | 'close' | 'stop'): void;
  setTemperature(id: string, value: number): void;
  setHvacMode(id: string, mode: string): void;
  mediaCommand(id: string, cmd: 'play_pause' | 'next' | 'prev'): void;
  setVolume(id: string, value: number): void;
  lockCommand(id: string, cmd: 'lock' | 'unlock'): void;
  alarmCommand(id: string, cmd: 'disarm' | 'arm_home' | 'arm_away' | 'arm_night'): void;
  vacuumCommand(id: string, cmd: 'start' | 'pause' | 'return_to_base'): void;
  activate(id: string): void;
};

const StoreCtx = React.createContext<Store | null>(null);
export const useStore = () => {
  const v = React.useContext(StoreCtx);
  if (!v) throw new Error('useStore outside StoreProvider');
  return v;
};

function mkActivity(e: Entity, message: string): ActivityEntry {
  return {
    id: `${e.id}-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
    ts: Date.now(),
    entityId: e.id,
    entityName: e.name,
    domain: e.domain,
    message,
  };
}

export function StoreProvider({ children }: { children: React.ReactNode }) {
  const [entities, setEntities] = React.useState<Record<string, Entity>>(() =>
    Object.fromEntries(INITIAL_ENTITIES.map(e => [e.id, e])),
  );
  const [activity, setActivity] = React.useState<ActivityEntry[]>([]);

  const log = React.useCallback((e: Entity, message: string) => {
    setActivity(prev => [mkActivity(e, message), ...prev].slice(0, 200));
  }, []);

  const mutate = React.useCallback(
    (id: string, fn: (e: Entity) => { next: Entity; msg: string } | null) => {
      setEntities(prev => {
        const cur = prev[id];
        if (!cur) return prev;
        const r = fn(cur);
        if (!r) return prev;
        log(r.next, r.msg);
        return { ...prev, [id]: r.next };
      });
    }, [log]);

  const toggle: Store['toggle'] = (id) => mutate(id, (e) => {
    /* Domain-aware toggle (correct semantics, like the Flutter client) */
    switch (e.domain) {
      case 'light': case 'switch': case 'fan': case 'input_boolean': case 'camera': {
        const next = { ...e, isOn: !e.isOn, state: !e.isOn ? 'on' : 'off',
          brightness: e.domain === 'light' && !e.isOn ? (e.brightness && e.brightness > 0 ? e.brightness : 180) : e.brightness };
        return { next, msg: next.isOn ? 'turned on' : 'turned off' };
      }
      case 'cover': {
        const opening = !e.isOn;
        return { next: { ...e, isOn: opening, state: opening ? 'open' : 'closed', position: opening ? 100 : 0 },
                 msg: opening ? 'opened' : 'closed' };
      }
      case 'lock': {
        const lock = e.state === 'unlocked';
        return { next: { ...e, isOn: !lock, state: lock ? 'locked' : 'unlocked' },
                 msg: lock ? 'locked' : 'unlocked' };
      }
      case 'media_player': {
        const playing = e.state === 'playing';
        return { next: { ...e, isOn: !playing, state: playing ? 'paused' : 'playing' },
                 msg: playing ? 'paused' : 'playing' };
      }
      case 'vacuum': {
        const cleaning = e.state === 'cleaning' || e.state === 'returning';
        return { next: { ...e, isOn: !cleaning, state: cleaning ? 'docked' : 'cleaning' },
                 msg: cleaning ? 'returning to dock' : 'cleaning' };
      }
      case 'climate': {
        const off = e.state === 'off';
        return { next: { ...e, isOn: off, state: off ? (e.hvacMode ?? 'heat') : 'off' },
                 msg: off ? 'on' : 'off' };
      }
      case 'scene': case 'script': case 'button': {
        return { next: { ...e }, msg: 'activated' };
      }
      default:
        return { next: { ...e, isOn: !e.isOn }, msg: !e.isOn ? 'on' : 'off' };
    }
  });

  const setBrightness: Store['setBrightness'] = (id, value) => mutate(id, (e) => ({
    next: { ...e, brightness: value, isOn: value > 0, state: value > 0 ? 'on' : 'off' },
    msg: `brightness ${Math.round((value / 255) * 100)}%`,
  }));

  const setPosition: Store['setPosition'] = (id, value) => mutate(id, (e) => ({
    next: { ...e, position: value, isOn: value > 0, state: value > 0 ? 'open' : 'closed' },
    msg: `position ${Math.round(value)}%`,
  }));

  const coverCommand: Store['coverCommand'] = (id, cmd) => mutate(id, (e) => {
    if (cmd === 'open') return { next: { ...e, isOn: true, state: 'open', position: 100 }, msg: 'opened' };
    if (cmd === 'close') return { next: { ...e, isOn: false, state: 'closed', position: 0 }, msg: 'closed' };
    return { next: e, msg: 'stop' };
  });

  const setTemperature: Store['setTemperature'] = (id, value) => mutate(id, (e) => ({
    next: { ...e, temperature: value }, msg: `setpoint ${value.toFixed(1)}°`,
  }));

  const setHvacMode: Store['setHvacMode'] = (id, mode) => mutate(id, (e) => ({
    next: { ...e, hvacMode: mode, state: mode, isOn: mode !== 'off' }, msg: `mode ${mode}`,
  }));

  const mediaCommand: Store['mediaCommand'] = (id, cmd) => mutate(id, (e) => {
    if (cmd === 'play_pause') {
      const playing = e.state === 'playing';
      return { next: { ...e, isOn: !playing, state: playing ? 'paused' : 'playing' },
               msg: playing ? 'paused' : 'playing' };
    }
    return { next: e, msg: cmd === 'next' ? 'next track' : 'previous track' };
  });

  const setVolume: Store['setVolume'] = (id, value) => mutate(id, (e) => ({
    next: { ...e, volume: value }, msg: `volume ${Math.round(value * 100)}%`,
  }));

  const lockCommand: Store['lockCommand'] = (id, cmd) => mutate(id, (e) => ({
    next: { ...e, state: cmd === 'lock' ? 'locked' : 'unlocked', isOn: cmd === 'unlock' },
    msg: cmd === 'lock' ? 'locked' : 'unlocked',
  }));

  const alarmCommand: Store['alarmCommand'] = (id, cmd) => mutate(id, (e) => ({
    next: { ...e, state: cmd === 'disarm' ? 'disarmed' : cmd, isOn: cmd !== 'disarm' },
    msg: cmd.replace('_', ' '),
  }));

  const vacuumCommand: Store['vacuumCommand'] = (id, cmd) => mutate(id, (e) => {
    if (cmd === 'start') return { next: { ...e, isOn: true, state: 'cleaning' }, msg: 'cleaning' };
    if (cmd === 'pause') return { next: { ...e, isOn: false, state: 'paused' }, msg: 'paused' };
    return { next: { ...e, isOn: false, state: 'docked' }, msg: 'returning to dock' };
  });

  const activate: Store['activate'] = (id) => mutate(id, (e) => ({
    next: e, msg: 'activated',
  }));

  return (
    <StoreCtx.Provider value={{
      entities, activity, toggle, setBrightness, setPosition, coverCommand,
      setTemperature, setHvacMode, mediaCommand, setVolume, lockCommand,
      alarmCommand, vacuumCommand, activate,
    }}>
      {children}
    </StoreCtx.Provider>
  );
}

/* ---------- Composite root provider ---------- */
export function AuroraProviders({ children }: { children: React.ReactNode }) {
  return (
    <SettingsProvider>
      <StoreProvider>
        {children}
      </StoreProvider>
    </SettingsProvider>
  );
}
