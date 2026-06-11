/* Aurora — shared types, sample HA-shaped data, theme tokens, dictionaries.
   Kept under a single _lib export so client components have one import path. */

export type Locale = 'fr' | 'en' | 'es' | 'de' | 'pt';
export type ThemeChoice = 'dark' | 'light' | 'dynamic';
export type BackgroundChoice = 'watermark' | 'slideshow' | 'none';

export type Entity = {
  id: string;
  name: string;
  domain: string;
  area: string;
  state: string;
  isOn: boolean;
  unit?: string;
  brightness?: number; // light, 0..255
  position?: number;   // cover, 0..100
  temperature?: number; // climate target
  hvacMode?: string;
  volume?: number; // 0..1
  mediaTitle?: string;
};

export type ActivityEntry = {
  id: string;
  ts: number;
  entityId: string;
  entityName: string;
  domain: string;
  message: string;
};

export type WeatherCondition = 'clear' | 'partly' | 'rain' | 'snow' | 'storm' | 'fog';
export type TimeOfDay = 'dawn' | 'day' | 'dusk' | 'night';

/* ---------- Accent + display helpers ---------- */

export const DOMAIN_ACCENT: Record<string, string> = {
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
  scene: '#F472B6',
  script: '#FB923C',
};
export const accentOf = (d: string) => DOMAIN_ACCENT[d] ?? '#818CF8';

/* ---------- Sample household ----------
   25 entities across 5 areas exercising every supported domain so every
   control surface in the entity sheet renders with real-looking data. */

export const INITIAL_ENTITIES: Entity[] = [
  // Living room
  { id: 'light.living_floor', name: 'Floor lamp', domain: 'light', area: 'living_room', state: 'on', isOn: true, brightness: 178 },
  { id: 'light.living_spotlights', name: 'Spotlights', domain: 'light', area: 'living_room', state: 'on', isOn: true, brightness: 125 },
  { id: 'media_player.living_sonos', name: 'Sonos', domain: 'media_player', area: 'living_room', state: 'playing', isOn: true, volume: 0.42, mediaTitle: 'Idaho — Ezra Collective' },
  { id: 'cover.living_blinds', name: 'Blinds', domain: 'cover', area: 'living_room', state: 'open', isOn: true, position: 100 },
  { id: 'climate.living_thermostat', name: 'Thermostat', domain: 'climate', area: 'living_room', state: 'heat', isOn: true, temperature: 21, hvacMode: 'heat' },
  // Kitchen
  { id: 'light.kitchen', name: 'Worktop', domain: 'light', area: 'kitchen', state: 'off', isOn: false, brightness: 0 },
  { id: 'sensor.fridge', name: 'Fridge', domain: 'sensor', area: 'kitchen', state: '4.1', isOn: false, unit: '°C' },
  { id: 'switch.kettle', name: 'Kettle', domain: 'switch', area: 'kitchen', state: 'off', isOn: false },
  { id: 'sensor.air_quality', name: 'Air quality', domain: 'sensor', area: 'kitchen', state: '38', isOn: false, unit: 'AQI' },
  // Bedroom
  { id: 'light.bedside', name: 'Bedside', domain: 'light', area: 'bedroom', state: 'off', isOn: false, brightness: 0 },
  { id: 'fan.ceiling', name: 'Ceiling fan', domain: 'fan', area: 'bedroom', state: 'off', isOn: false },
  { id: 'climate.bedroom_ac', name: 'AC', domain: 'climate', area: 'bedroom', state: 'cool', isOn: true, temperature: 23, hvacMode: 'cool' },
  // Entryway
  { id: 'lock.front_door', name: 'Front door', domain: 'lock', area: 'entryway', state: 'locked', isOn: false },
  { id: 'alarm_control_panel.home', name: 'Alarm', domain: 'alarm_control_panel', area: 'entryway', state: 'armed_home', isOn: true },
  { id: 'camera.porch', name: 'Porch cam', domain: 'camera', area: 'entryway', state: 'streaming', isOn: true },
  { id: 'binary_sensor.motion_hall', name: 'Hallway motion', domain: 'binary_sensor', area: 'entryway', state: 'off', isOn: false },
  // Outside
  { id: 'cover.garage', name: 'Garage', domain: 'cover', area: 'outside', state: 'closed', isOn: false, position: 0 },
  { id: 'vacuum.roomba', name: 'Roomba', domain: 'vacuum', area: 'outside', state: 'docked', isOn: false },
  { id: 'switch.garden_pump', name: 'Garden pump', domain: 'switch', area: 'outside', state: 'off', isOn: false },
  { id: 'light.driveway', name: 'Driveway lights', domain: 'light', area: 'outside', state: 'on', isOn: true, brightness: 200 },
  // Scenes (live on the dashboard top, not in an area)
  { id: 'scene.movie_night', name: 'Movie night', domain: 'scene', area: 'living_room', state: 'scening', isOn: false },
  { id: 'scene.bedtime', name: 'Bedtime', domain: 'scene', area: 'bedroom', state: 'scening', isOn: false },
];

/* Translate snake_case area keys into i18n strings via dictionary. */
export const AREA_KEYS = ['living_room', 'kitchen', 'bedroom', 'entryway', 'outside'] as const;
export type AreaKey = typeof AREA_KEYS[number];
export const isAreaKey = (s: string): s is AreaKey =>
  (AREA_KEYS as readonly string[]).includes(s);

/* ---------- Dictionaries ---------- */

export type DictKey =
  | 'app.tagline'
  | 'top.connected' | 'top.menu' | 'top.settings'
  | 'pulse.title' | 'pulse.calm' | 'pulse.active' | 'pulse.devicesLive'
  | 'pulse.indoor' | 'pulse.humidity' | 'pulse.lightsOn' | 'pulse.atHome' | 'pulse.acrossAreas'
  | 'chips.allClear'
  | 'state.home' | 'state.away'
  | 'area.living_room' | 'area.kitchen' | 'area.bedroom' | 'area.entryway' | 'area.outside'
  | 'area.active' | 'area.devices' | 'area.viewAll'
  | 'activity.title' | 'activity.lastMin' | 'activity.empty' | 'activity.allQuiet'
  | 'activity.full' | 'activity.back'
  | 'sheet.on' | 'sheet.off' | 'sheet.brightness' | 'sheet.speed' | 'sheet.volume'
  | 'sheet.position' | 'sheet.open' | 'sheet.close' | 'sheet.stop'
  | 'sheet.lock' | 'sheet.unlock'
  | 'sheet.armHome' | 'sheet.armAway' | 'sheet.armNight' | 'sheet.disarm' | 'sheet.code'
  | 'sheet.target' | 'sheet.heat' | 'sheet.cool' | 'sheet.auto' | 'sheet.dry' | 'sheet.fan' | 'sheet.modes'
  | 'sheet.play' | 'sheet.pause' | 'sheet.next' | 'sheet.prev' | 'sheet.nowPlaying'
  | 'sheet.activate' | 'sheet.run' | 'sheet.startCleaning' | 'sheet.returnDock' | 'sheet.pauseClean'
  | 'sheet.attributes'
  | 'settings.title' | 'settings.theme' | 'settings.theme.dark' | 'settings.theme.light' | 'settings.theme.dynamic'
  | 'settings.theme.dynamicHint'
  | 'settings.background' | 'settings.bg.watermark' | 'settings.bg.slideshow' | 'settings.bg.none'
  | 'settings.bg.watermarkHint' | 'settings.bg.slideshowHint' | 'settings.bg.noneHint'
  | 'settings.language' | 'settings.connection' | 'settings.connectionHint' | 'settings.about' | 'settings.aboutBody'
  | 'settings.weather.label' | 'settings.weather.clear' | 'settings.weather.partly' | 'settings.weather.rain' | 'settings.weather.snow' | 'settings.weather.storm' | 'settings.weather.fog'
  | 'settings.tod.dawn' | 'settings.tod.day' | 'settings.tod.dusk' | 'settings.tod.night'
  | 'nav.dashboard' | 'nav.activity' | 'nav.settings';

export type Dictionary = Record<DictKey, string>;

const fr: Dictionary = {
  'app.tagline': 'Aperçu Aurora',
  'top.connected': 'Connecté — Home Assistant',
  'top.menu': 'Menu', 'top.settings': 'Paramètres',
  'pulse.title': 'Pouls de la maison',
  'pulse.calm': 'Calme', 'pulse.active': 'Actif',
  'pulse.devicesLive': '{n} appareils actifs',
  'pulse.indoor': 'Intérieur', 'pulse.humidity': 'Humidité',
  'pulse.lightsOn': 'Lumières allumées', 'pulse.atHome': 'À la maison',
  'pulse.acrossAreas': 'sur {n} pièces',
  'chips.allClear': 'Tout va bien',
  'state.home': 'maison', 'state.away': 'absent',
  'area.living_room': 'Salon', 'area.kitchen': 'Cuisine', 'area.bedroom': 'Chambre',
  'area.entryway': 'Entrée', 'area.outside': 'Extérieur',
  'area.active': 'actifs', 'area.devices': 'appareils', 'area.viewAll': 'Tout voir',
  'activity.title': 'Activité en direct', 'activity.lastMin': '{n} événements · 5 dern. min',
  'activity.empty': 'Aucune activité', 'activity.allQuiet': 'tout est calme',
  'activity.full': "Flux d'activité", 'activity.back': 'Retour',
  'sheet.on': 'Allumé', 'sheet.off': 'Éteint',
  'sheet.brightness': 'Luminosité', 'sheet.speed': 'Vitesse', 'sheet.volume': 'Volume',
  'sheet.position': 'Position', 'sheet.open': 'Ouvrir', 'sheet.close': 'Fermer', 'sheet.stop': 'Stop',
  'sheet.lock': 'Verrouiller', 'sheet.unlock': 'Déverrouiller',
  'sheet.armHome': 'Armer maison', 'sheet.armAway': 'Armer absent', 'sheet.armNight': 'Armer nuit',
  'sheet.disarm': 'Désarmer', 'sheet.code': 'Code',
  'sheet.target': 'Consigne', 'sheet.heat': 'Chauffage', 'sheet.cool': 'Clim', 'sheet.auto': 'Auto',
  'sheet.dry': 'Déshu', 'sheet.fan': 'Ventil', 'sheet.modes': 'Modes',
  'sheet.play': 'Lire', 'sheet.pause': 'Pause', 'sheet.next': 'Suivant', 'sheet.prev': 'Précédent',
  'sheet.nowPlaying': 'En lecture',
  'sheet.activate': 'Activer', 'sheet.run': 'Lancer',
  'sheet.startCleaning': 'Démarrer', 'sheet.returnDock': 'Retour station', 'sheet.pauseClean': 'Pause',
  'sheet.attributes': 'Attributs',
  'settings.title': 'Paramètres',
  'settings.theme': 'Thème',
  'settings.theme.dark': 'Sombre', 'settings.theme.light': 'Clair', 'settings.theme.dynamic': 'Dynamique',
  'settings.theme.dynamicHint': "S'adapte à l'heure et à la météo locale.",
  'settings.background': 'Arrière-plan',
  'settings.bg.watermark': 'Filigrane SafeR', 'settings.bg.slideshow': 'Diaporama produits', 'settings.bg.none': 'Aucun',
  'settings.bg.watermarkHint': 'Logo SafeR estompé à 10 % d’opacité.',
  'settings.bg.slideshowHint': '100 illustrations d’appareils, défilement lent.',
  'settings.bg.noneHint': 'Surface unie sans superposition.',
  'settings.language': 'Langue',
  'settings.connection': 'Connexion Home Assistant',
  'settings.connectionHint': 'URL et jeton renseignés depuis l’app mobile Flutter.',
  'settings.about': 'À propos',
  'settings.aboutBody': 'SafeR Mobile — design Aurora pour Home Assistant.',
  'settings.weather.label': 'Météo',
  'settings.weather.clear': 'Dégagé', 'settings.weather.partly': 'Nuages',
  'settings.weather.rain': 'Pluie', 'settings.weather.snow': 'Neige',
  'settings.weather.storm': 'Orage', 'settings.weather.fog': 'Brouillard',
  'settings.tod.dawn': 'Aube', 'settings.tod.day': 'Jour', 'settings.tod.dusk': 'Crépuscule', 'settings.tod.night': 'Nuit',
  'nav.dashboard': 'Tableau', 'nav.activity': 'Activité', 'nav.settings': 'Réglages',
};

const en: Dictionary = {
  'app.tagline': 'Aurora preview',
  'top.connected': 'Connected — Home Assistant',
  'top.menu': 'Menu', 'top.settings': 'Settings',
  'pulse.title': 'Home pulse',
  'pulse.calm': 'Calm', 'pulse.active': 'Active',
  'pulse.devicesLive': '{n} devices live',
  'pulse.indoor': 'Indoor', 'pulse.humidity': 'Humidity',
  'pulse.lightsOn': 'Lights on', 'pulse.atHome': 'At home',
  'pulse.acrossAreas': 'across {n} areas',
  'chips.allClear': 'All clear',
  'state.home': 'home', 'state.away': 'away',
  'area.living_room': 'Living room', 'area.kitchen': 'Kitchen', 'area.bedroom': 'Bedroom',
  'area.entryway': 'Entryway', 'area.outside': 'Outside',
  'area.active': 'active', 'area.devices': 'devices', 'area.viewAll': 'View all',
  'activity.title': 'Live activity', 'activity.lastMin': '{n} events · last 5 min',
  'activity.empty': 'No activity yet', 'activity.allQuiet': 'all quiet',
  'activity.full': 'Activity feed', 'activity.back': 'Back',
  'sheet.on': 'On', 'sheet.off': 'Off',
  'sheet.brightness': 'Brightness', 'sheet.speed': 'Speed', 'sheet.volume': 'Volume',
  'sheet.position': 'Position', 'sheet.open': 'Open', 'sheet.close': 'Close', 'sheet.stop': 'Stop',
  'sheet.lock': 'Lock', 'sheet.unlock': 'Unlock',
  'sheet.armHome': 'Arm home', 'sheet.armAway': 'Arm away', 'sheet.armNight': 'Arm night',
  'sheet.disarm': 'Disarm', 'sheet.code': 'Code',
  'sheet.target': 'Target', 'sheet.heat': 'Heat', 'sheet.cool': 'Cool', 'sheet.auto': 'Auto',
  'sheet.dry': 'Dry', 'sheet.fan': 'Fan', 'sheet.modes': 'Modes',
  'sheet.play': 'Play', 'sheet.pause': 'Pause', 'sheet.next': 'Next', 'sheet.prev': 'Previous',
  'sheet.nowPlaying': 'Now playing',
  'sheet.activate': 'Activate', 'sheet.run': 'Run',
  'sheet.startCleaning': 'Start', 'sheet.returnDock': 'Return to dock', 'sheet.pauseClean': 'Pause',
  'sheet.attributes': 'Attributes',
  'settings.title': 'Settings',
  'settings.theme': 'Theme',
  'settings.theme.dark': 'Dark', 'settings.theme.light': 'Light', 'settings.theme.dynamic': 'Dynamic',
  'settings.theme.dynamicHint': 'Adapts to time of day and local weather.',
  'settings.background': 'Background',
  'settings.bg.watermark': 'SafeR watermark', 'settings.bg.slideshow': 'Product slideshow', 'settings.bg.none': 'None',
  'settings.bg.watermarkHint': 'Soft SafeR logo at 10% opacity.',
  'settings.bg.slideshowHint': '100 device illustrations, slowly cycling.',
  'settings.bg.noneHint': 'Plain surface, no overlay.',
  'settings.language': 'Language',
  'settings.connection': 'Home Assistant connection',
  'settings.connectionHint': 'URL and token are set from the Flutter mobile app.',
  'settings.about': 'About',
  'settings.aboutBody': 'SafeR Mobile — Aurora design for Home Assistant.',
  'settings.weather.label': 'Weather',
  'settings.weather.clear': 'Clear', 'settings.weather.partly': 'Cloudy',
  'settings.weather.rain': 'Rain', 'settings.weather.snow': 'Snow',
  'settings.weather.storm': 'Storm', 'settings.weather.fog': 'Fog',
  'settings.tod.dawn': 'Dawn', 'settings.tod.day': 'Day', 'settings.tod.dusk': 'Dusk', 'settings.tod.night': 'Night',
  'nav.dashboard': 'Dashboard', 'nav.activity': 'Activity', 'nav.settings': 'Settings',
};

const es: Dictionary = {
  'app.tagline': 'Vista previa Aurora',
  'top.connected': 'Conectado — Home Assistant',
  'top.menu': 'Menú', 'top.settings': 'Ajustes',
  'pulse.title': 'Pulso del hogar',
  'pulse.calm': 'Tranquilo', 'pulse.active': 'Activo',
  'pulse.devicesLive': '{n} dispositivos activos',
  'pulse.indoor': 'Interior', 'pulse.humidity': 'Humedad',
  'pulse.lightsOn': 'Luces encendidas', 'pulse.atHome': 'En casa',
  'pulse.acrossAreas': 'en {n} áreas',
  'chips.allClear': 'Todo en orden',
  'state.home': 'en casa', 'state.away': 'fuera',
  'area.living_room': 'Salón', 'area.kitchen': 'Cocina', 'area.bedroom': 'Dormitorio',
  'area.entryway': 'Entrada', 'area.outside': 'Exterior',
  'area.active': 'activos', 'area.devices': 'dispositivos', 'area.viewAll': 'Ver todo',
  'activity.title': 'Actividad en vivo', 'activity.lastMin': '{n} eventos · últ. 5 min',
  'activity.empty': 'Sin actividad', 'activity.allQuiet': 'todo tranquilo',
  'activity.full': 'Historial de actividad', 'activity.back': 'Volver',
  'sheet.on': 'Encendido', 'sheet.off': 'Apagado',
  'sheet.brightness': 'Brillo', 'sheet.speed': 'Velocidad', 'sheet.volume': 'Volumen',
  'sheet.position': 'Posición', 'sheet.open': 'Abrir', 'sheet.close': 'Cerrar', 'sheet.stop': 'Detener',
  'sheet.lock': 'Bloquear', 'sheet.unlock': 'Desbloquear',
  'sheet.armHome': 'Armar casa', 'sheet.armAway': 'Armar fuera', 'sheet.armNight': 'Armar noche',
  'sheet.disarm': 'Desarmar', 'sheet.code': 'Código',
  'sheet.target': 'Objetivo', 'sheet.heat': 'Calor', 'sheet.cool': 'Frío', 'sheet.auto': 'Auto',
  'sheet.dry': 'Seco', 'sheet.fan': 'Ventilador', 'sheet.modes': 'Modos',
  'sheet.play': 'Reproducir', 'sheet.pause': 'Pausa', 'sheet.next': 'Siguiente', 'sheet.prev': 'Anterior',
  'sheet.nowPlaying': 'Reproduciendo',
  'sheet.activate': 'Activar', 'sheet.run': 'Ejecutar',
  'sheet.startCleaning': 'Iniciar', 'sheet.returnDock': 'Volver a base', 'sheet.pauseClean': 'Pausa',
  'sheet.attributes': 'Atributos',
  'settings.title': 'Ajustes',
  'settings.theme': 'Tema',
  'settings.theme.dark': 'Oscuro', 'settings.theme.light': 'Claro', 'settings.theme.dynamic': 'Dinámico',
  'settings.theme.dynamicHint': 'Se adapta a la hora del día y al clima local.',
  'settings.background': 'Fondo',
  'settings.bg.watermark': 'Marca de agua SafeR', 'settings.bg.slideshow': 'Diapositivas productos', 'settings.bg.none': 'Ninguno',
  'settings.bg.watermarkHint': 'Logo SafeR al 10% de opacidad.',
  'settings.bg.slideshowHint': '100 ilustraciones de dispositivos en bucle.',
  'settings.bg.noneHint': 'Superficie sin superposición.',
  'settings.language': 'Idioma',
  'settings.connection': 'Conexión Home Assistant',
  'settings.connectionHint': 'URL y token se configuran desde la app móvil Flutter.',
  'settings.about': 'Acerca de',
  'settings.aboutBody': 'SafeR Mobile — diseño Aurora para Home Assistant.',
  'settings.weather.label': 'Clima',
  'settings.weather.clear': 'Despejado', 'settings.weather.partly': 'Nublado',
  'settings.weather.rain': 'Lluvia', 'settings.weather.snow': 'Nieve',
  'settings.weather.storm': 'Tormenta', 'settings.weather.fog': 'Niebla',
  'settings.tod.dawn': 'Amanecer', 'settings.tod.day': 'Día', 'settings.tod.dusk': 'Atardecer', 'settings.tod.night': 'Noche',
  'nav.dashboard': 'Panel', 'nav.activity': 'Actividad', 'nav.settings': 'Ajustes',
};

const de: Dictionary = {
  'app.tagline': 'Aurora-Vorschau',
  'top.connected': 'Verbunden — Home Assistant',
  'top.menu': 'Menü', 'top.settings': 'Einstellungen',
  'pulse.title': 'Haus-Puls',
  'pulse.calm': 'Ruhig', 'pulse.active': 'Aktiv',
  'pulse.devicesLive': '{n} Geräte aktiv',
  'pulse.indoor': 'Innen', 'pulse.humidity': 'Feuchte',
  'pulse.lightsOn': 'Lichter an', 'pulse.atHome': 'Zu Hause',
  'pulse.acrossAreas': 'in {n} Räumen',
  'chips.allClear': 'Alles ruhig',
  'state.home': 'zu Hause', 'state.away': 'unterwegs',
  'area.living_room': 'Wohnzimmer', 'area.kitchen': 'Küche', 'area.bedroom': 'Schlafzimmer',
  'area.entryway': 'Eingang', 'area.outside': 'Außen',
  'area.active': 'aktiv', 'area.devices': 'Geräte', 'area.viewAll': 'Alle anzeigen',
  'activity.title': 'Live-Aktivität', 'activity.lastMin': '{n} Ereignisse · letzte 5 Min',
  'activity.empty': 'Keine Aktivität', 'activity.allQuiet': 'alles still',
  'activity.full': 'Aktivitätsverlauf', 'activity.back': 'Zurück',
  'sheet.on': 'An', 'sheet.off': 'Aus',
  'sheet.brightness': 'Helligkeit', 'sheet.speed': 'Stufe', 'sheet.volume': 'Lautstärke',
  'sheet.position': 'Position', 'sheet.open': 'Öffnen', 'sheet.close': 'Schließen', 'sheet.stop': 'Stop',
  'sheet.lock': 'Sperren', 'sheet.unlock': 'Entsperren',
  'sheet.armHome': 'Aktivieren Zuhause', 'sheet.armAway': 'Aktivieren abwesend', 'sheet.armNight': 'Aktivieren Nacht',
  'sheet.disarm': 'Deaktivieren', 'sheet.code': 'Code',
  'sheet.target': 'Sollwert', 'sheet.heat': 'Heizen', 'sheet.cool': 'Kühlen', 'sheet.auto': 'Auto',
  'sheet.dry': 'Trocken', 'sheet.fan': 'Lüfter', 'sheet.modes': 'Modi',
  'sheet.play': 'Wiedergabe', 'sheet.pause': 'Pause', 'sheet.next': 'Weiter', 'sheet.prev': 'Zurück',
  'sheet.nowPlaying': 'Läuft',
  'sheet.activate': 'Aktivieren', 'sheet.run': 'Ausführen',
  'sheet.startCleaning': 'Starten', 'sheet.returnDock': 'Zur Station', 'sheet.pauseClean': 'Pause',
  'sheet.attributes': 'Attribute',
  'settings.title': 'Einstellungen',
  'settings.theme': 'Design',
  'settings.theme.dark': 'Dunkel', 'settings.theme.light': 'Hell', 'settings.theme.dynamic': 'Dynamisch',
  'settings.theme.dynamicHint': 'Passt sich Tageszeit und lokalem Wetter an.',
  'settings.background': 'Hintergrund',
  'settings.bg.watermark': 'SafeR-Wasserzeichen', 'settings.bg.slideshow': 'Produkt-Slideshow', 'settings.bg.none': 'Keiner',
  'settings.bg.watermarkHint': 'SafeR-Logo bei 10 % Deckkraft.',
  'settings.bg.slideshowHint': '100 Gerätegrafiken, langsam wechselnd.',
  'settings.bg.noneHint': 'Reine Oberfläche, keine Überlagerung.',
  'settings.language': 'Sprache',
  'settings.connection': 'Home-Assistant-Verbindung',
  'settings.connectionHint': 'URL und Token werden in der Flutter-App gesetzt.',
  'settings.about': 'Über',
  'settings.aboutBody': 'SafeR Mobile — Aurora-Design für Home Assistant.',
  'settings.weather.label': 'Wetter',
  'settings.weather.clear': 'Klar', 'settings.weather.partly': 'Bewölkt',
  'settings.weather.rain': 'Regen', 'settings.weather.snow': 'Schnee',
  'settings.weather.storm': 'Gewitter', 'settings.weather.fog': 'Nebel',
  'settings.tod.dawn': 'Dämmerung', 'settings.tod.day': 'Tag', 'settings.tod.dusk': 'Abend', 'settings.tod.night': 'Nacht',
  'nav.dashboard': 'Übersicht', 'nav.activity': 'Aktivität', 'nav.settings': 'Einstellungen',
};

const pt: Dictionary = {
  'app.tagline': 'Pré-visualização Aurora',
  'top.connected': 'Conectado — Home Assistant',
  'top.menu': 'Menu', 'top.settings': 'Configurações',
  'pulse.title': 'Pulso de casa',
  'pulse.calm': 'Tranquilo', 'pulse.active': 'Ativo',
  'pulse.devicesLive': '{n} dispositivos ativos',
  'pulse.indoor': 'Interior', 'pulse.humidity': 'Humidade',
  'pulse.lightsOn': 'Luzes ligadas', 'pulse.atHome': 'Em casa',
  'pulse.acrossAreas': 'em {n} divisões',
  'chips.allClear': 'Tudo tranquilo',
  'state.home': 'em casa', 'state.away': 'fora',
  'area.living_room': 'Sala', 'area.kitchen': 'Cozinha', 'area.bedroom': 'Quarto',
  'area.entryway': 'Entrada', 'area.outside': 'Exterior',
  'area.active': 'ativos', 'area.devices': 'dispositivos', 'area.viewAll': 'Ver tudo',
  'activity.title': 'Atividade ao vivo', 'activity.lastMin': '{n} eventos · últ. 5 min',
  'activity.empty': 'Sem atividade', 'activity.allQuiet': 'tudo calmo',
  'activity.full': 'Histórico de atividade', 'activity.back': 'Voltar',
  'sheet.on': 'Ligado', 'sheet.off': 'Desligado',
  'sheet.brightness': 'Brilho', 'sheet.speed': 'Velocidade', 'sheet.volume': 'Volume',
  'sheet.position': 'Posição', 'sheet.open': 'Abrir', 'sheet.close': 'Fechar', 'sheet.stop': 'Parar',
  'sheet.lock': 'Trancar', 'sheet.unlock': 'Destrancar',
  'sheet.armHome': 'Armar casa', 'sheet.armAway': 'Armar fora', 'sheet.armNight': 'Armar noite',
  'sheet.disarm': 'Desarmar', 'sheet.code': 'Código',
  'sheet.target': 'Alvo', 'sheet.heat': 'Aquecer', 'sheet.cool': 'Arrefecer', 'sheet.auto': 'Auto',
  'sheet.dry': 'Seco', 'sheet.fan': 'Ventoinha', 'sheet.modes': 'Modos',
  'sheet.play': 'Tocar', 'sheet.pause': 'Pausa', 'sheet.next': 'Próx.', 'sheet.prev': 'Anterior',
  'sheet.nowPlaying': 'A tocar',
  'sheet.activate': 'Ativar', 'sheet.run': 'Executar',
  'sheet.startCleaning': 'Iniciar', 'sheet.returnDock': 'Voltar à doca', 'sheet.pauseClean': 'Pausa',
  'sheet.attributes': 'Atributos',
  'settings.title': 'Configurações',
  'settings.theme': 'Tema',
  'settings.theme.dark': 'Escuro', 'settings.theme.light': 'Claro', 'settings.theme.dynamic': 'Dinâmico',
  'settings.theme.dynamicHint': 'Adapta-se à hora do dia e ao clima local.',
  'settings.background': 'Fundo',
  'settings.bg.watermark': 'Marca de água SafeR', 'settings.bg.slideshow': 'Apresentação produtos', 'settings.bg.none': 'Nenhum',
  'settings.bg.watermarkHint': 'Logo SafeR a 10 % de opacidade.',
  'settings.bg.slideshowHint': '100 ilustrações de dispositivos em rotação.',
  'settings.bg.noneHint': 'Superfície limpa, sem sobreposição.',
  'settings.language': 'Idioma',
  'settings.connection': 'Ligação Home Assistant',
  'settings.connectionHint': 'URL e token definidos na app móvel Flutter.',
  'settings.about': 'Sobre',
  'settings.aboutBody': 'SafeR Mobile — design Aurora para Home Assistant.',
  'settings.weather.label': 'Clima',
  'settings.weather.clear': 'Limpo', 'settings.weather.partly': 'Nublado',
  'settings.weather.rain': 'Chuva', 'settings.weather.snow': 'Neve',
  'settings.weather.storm': 'Tempestade', 'settings.weather.fog': 'Nevoeiro',
  'settings.tod.dawn': 'Madrugada', 'settings.tod.day': 'Dia', 'settings.tod.dusk': 'Crepúsculo', 'settings.tod.night': 'Noite',
  'nav.dashboard': 'Painel', 'nav.activity': 'Atividade', 'nav.settings': 'Configurações',
};

export const DICTIONARIES: Record<Locale, Dictionary> = { fr, en, es, de, pt };

export const LOCALE_LABELS: Record<Locale, string> = {
  fr: 'Français', en: 'English', es: 'Español', de: 'Deutsch', pt: 'Português',
};

/* ---------- Theme tokens ---------- */

export type ThemeTokens = {
  /** Resolved mode after dynamic resolution. */
  mode: 'dark' | 'light';
  /** Optional descriptor when dynamic mode resolves (dawn/day/dusk/night + weather). */
  variant?: string;
  /** Main page background (CSS gradient). */
  background: string;
  /** Three aurora wash colors (radials behind content). */
  washes: [string, string, string];
  /** Card glass color + border + shadow. */
  glass: string;
  glassBorder: string;
  shadow: string;
  /** Text colors. */
  text: string;
  textSubtle: string;
  textFaint: string;
  /** Glass border for active tiles. */
  activeBorder: string;
};

export const DARK_TOKENS: ThemeTokens = {
  mode: 'dark',
  background: 'linear-gradient(135deg, #06081C 0%, #0E1138 45%, #1B0838 100%)',
  washes: ['#14B8A6', '#F59E0B', '#818CF8'],
  glass: 'rgba(255,255,255,0.04)',
  glassBorder: 'rgba(255,255,255,0.08)',
  shadow: 'rgba(0,0,0,0.4)',
  text: 'rgba(255,255,255,0.92)',
  textSubtle: 'rgba(255,255,255,0.55)',
  textFaint: 'rgba(255,255,255,0.4)',
  activeBorder: 'rgba(255,255,255,0.12)',
};

export const LIGHT_TOKENS: ThemeTokens = {
  mode: 'light',
  background: 'linear-gradient(135deg, #F0F4FF 0%, #FFF7ED 50%, #FDF2F8 100%)',
  washes: ['#5EEAD4', '#FCD34D', '#A5B4FC'],
  glass: 'rgba(255,255,255,0.55)',
  glassBorder: 'rgba(15,23,42,0.08)',
  shadow: 'rgba(15,23,42,0.08)',
  text: 'rgba(15,23,42,0.92)',
  textSubtle: 'rgba(15,23,42,0.55)',
  textFaint: 'rgba(15,23,42,0.4)',
  activeBorder: 'rgba(15,23,42,0.14)',
};

/** Time-of-day + weather → token set (dynamic mode). */
export function resolveDynamicTokens(now: Date, weather: WeatherCondition): ThemeTokens {
  const h = now.getHours();
  const tod: TimeOfDay =
    h >= 5 && h < 8 ? 'dawn' :
    h >= 8 && h < 17 ? 'day' :
    h >= 17 && h < 20 ? 'dusk' :
    'night';

  /* Time-of-day base */
  let bg: string;
  let washes: [string, string, string];
  let mode: 'dark' | 'light' = 'dark';
  switch (tod) {
    case 'dawn':
      mode = 'light';
      bg = 'linear-gradient(135deg, #FFE4D6 0%, #FFD1B3 45%, #FBC2D4 100%)';
      washes = ['#FBBF24', '#F472B6', '#FCD34D']; break;
    case 'day':
      mode = 'light';
      bg = 'linear-gradient(135deg, #DBEAFE 0%, #BAE6FD 45%, #E0F2FE 100%)';
      washes = ['#60A5FA', '#34D399', '#FBBF24']; break;
    case 'dusk':
      mode = 'dark';
      bg = 'linear-gradient(135deg, #4C1D95 0%, #831843 45%, #92400E 100%)';
      washes = ['#FB923C', '#A78BFA', '#F472B6']; break;
    default:
      mode = 'dark';
      bg = 'linear-gradient(135deg, #020617 0%, #0B0F29 45%, #1B0838 100%)';
      washes = ['#14B8A6', '#818CF8', '#7C3AED']; break;
  }

  /* Weather modifier — tint a wash and (for rain/storm) cool things down */
  switch (weather) {
    case 'rain':
      washes = [washes[0], '#38BDF8', washes[2]];
      bg = mode === 'dark'
        ? 'linear-gradient(135deg, #0F172A 0%, #1E293B 50%, #312E81 100%)'
        : 'linear-gradient(135deg, #CFFAFE 0%, #BFDBFE 45%, #DBEAFE 100%)';
      break;
    case 'storm':
      mode = 'dark';
      washes = ['#A78BFA', '#7C3AED', '#38BDF8'];
      bg = 'linear-gradient(135deg, #0B1024 0%, #1F1147 45%, #2A1065 100%)';
      break;
    case 'snow':
      mode = 'light';
      washes = ['#E0F2FE', '#A5F3FC', '#C7D2FE'];
      bg = 'linear-gradient(135deg, #F8FAFC 0%, #E0F2FE 50%, #EEF2FF 100%)';
      break;
    case 'fog':
      washes = [washes[0], '#94A3B8', washes[2]];
      break;
    case 'partly':
      washes = [washes[0], washes[1], '#94A3B8'];
      break;
    /* clear: leave the time-of-day defaults alone */
  }

  const base = mode === 'dark' ? DARK_TOKENS : LIGHT_TOKENS;
  return { ...base, background: bg, washes, variant: `${tod}·${weather}` };
}

/* WMO code → our condition bucket. */
export function weatherFromCode(code: number | undefined): WeatherCondition {
  if (code === undefined) return 'clear';
  if (code === 0) return 'clear';
  if (code >= 1 && code <= 3) return 'partly';
  if (code >= 45 && code <= 48) return 'fog';
  if ((code >= 51 && code <= 67) || (code >= 80 && code <= 82)) return 'rain';
  if (code >= 71 && code <= 77) return 'snow';
  if (code >= 95 && code <= 99) return 'storm';
  return 'clear';
}

/* ---------- 100 procedurally-generated product slides ----------
   12 device archetypes × 10 palettes (rotated/shaded) = 120 → take 100.
   Each slide is a pure SVG so there's no asset/network dependency. */

const SLIDE_DEVICES = [
  'bulb', 'lock', 'thermostat', 'camera', 'sensor', 'plug',
  'speaker', 'hub', 'fan', 'cover', 'vacuum', 'panel',
] as const;
type Slide = { device: typeof SLIDE_DEVICES[number]; accent: string; hue: string; key: string };

const SLIDE_PALETTES = [
  ['#FBBF24', '#F59E0B'], ['#60A5FA', '#3B82F6'], ['#A78BFA', '#7C3AED'],
  ['#F87171', '#DC2626'], ['#34D399', '#10B981'], ['#2DD4BF', '#0D9488'],
  ['#F472B6', '#DB2777'], ['#FB923C', '#EA580C'], ['#818CF8', '#4F46E5'],
  ['#C084FC', '#9333EA'],
];

export function buildSlides(): Slide[] {
  const out: Slide[] = [];
  for (let i = 0; i < 100; i++) {
    const dev = SLIDE_DEVICES[i % SLIDE_DEVICES.length];
    const pal = SLIDE_PALETTES[(i * 7) % SLIDE_PALETTES.length];
    out.push({ device: dev, accent: pal[0], hue: pal[1], key: `${dev}-${i}` });
  }
  return out;
}
