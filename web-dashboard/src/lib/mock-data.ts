import { Incident } from '@/types/incident';

// Demo incidents around Abidjan
export const MOCK_INCIDENTS: Incident[] = [
  {
    id: '1',
    incident_type: 'panic',
    severity: 'critical',
    status: 'open',
    location_lat: 5.3600,
    location_lon: -4.0083,
    location_name: 'Cocody, Abidjan',
    commune: 'Cocody',
    description: 'Bouton panique activé — Zone résidentielle',
    created_at: new Date(Date.now() - 5 * 60000).toISOString(),
    source: 'ha_node',
  },
  {
    id: '2',
    incident_type: 'fire',
    severity: 'high',
    status: 'responding',
    location_lat: 5.3469,
    location_lon: -4.0167,
    location_name: 'Marcory, Abidjan',
    commune: 'Marcory',
    description: 'Fumée détectée — Bâtiment commercial',
    created_at: new Date(Date.now() - 22 * 60000).toISOString(),
    source: 'ha_node',
  },
  {
    id: '3',
    incident_type: 'flood',
    severity: 'medium',
    status: 'acknowledged',
    location_lat: 5.3264,
    location_lon: -4.0186,
    location_name: 'Koumassi, Abidjan',
    commune: 'Koumassi',
    description: 'Capteur inondation déclenché — Zone basse',
    created_at: new Date(Date.now() - 47 * 60000).toISOString(),
    source: 'ha_node',
  },
  {
    id: '4',
    incident_type: 'medical',
    severity: 'high',
    status: 'open',
    location_lat: 5.3667,
    location_lon: -4.0321,
    location_name: 'Yopougon, Abidjan',
    commune: 'Yopougon',
    description: 'Urgence médicale signalée via application',
    created_at: new Date(Date.now() - 8 * 60000).toISOString(),
    source: 'mobile_app',
  },
  {
    id: '5',
    incident_type: 'accident',
    severity: 'medium',
    status: 'resolved',
    location_lat: 5.3414,
    location_lon: -4.0289,
    location_name: 'Abobo, Abidjan',
    commune: 'Abobo',
    description: 'Accident de la route signalé',
    created_at: new Date(Date.now() - 2 * 3600000).toISOString(),
    source: 'mobile_app',
  },
  {
    id: '6',
    incident_type: 'panic',
    severity: 'critical',
    status: 'resolved',
    location_lat: 5.3564,
    location_lon: -3.9808,
    location_name: 'Plateau, Abidjan',
    commune: 'Plateau',
    description: 'Alerte SOS — Centre-ville',
    created_at: new Date(Date.now() - 4 * 3600000).toISOString(),
    source: 'mobile_app',
  },
];

export function getStats(incidents: Incident[]) {
  const open = incidents.filter(i => i.status === 'open').length;
  const critical = incidents.filter(i => i.severity === 'critical' && i.status !== 'resolved').length;
  const responding = incidents.filter(i => i.status === 'responding').length;
  const resolved = incidents.filter(i => i.status === 'resolved').length;
  return { open, critical, responding, resolved, total: incidents.length };
}

export function timeAgo(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'À l\'instant';
  if (mins < 60) return `Il y a ${mins} min`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `Il y a ${hrs}h`;
  return `Il y a ${Math.floor(hrs / 24)}j`;
}
