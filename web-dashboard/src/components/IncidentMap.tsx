'use client';
import { useEffect, useRef } from 'react';
import { Incident, INCIDENT_COLORS } from '@/types/incident';

interface IncidentMapProps {
  incidents: Incident[];
}

export default function IncidentMap({ incidents }: IncidentMapProps) {
  const mapRef = useRef<any>(null);
  const mapContainerRef = useRef<HTMLDivElement>(null);
  const markersRef = useRef<any[]>([]);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    if (mapRef.current) return;

    if (!document.getElementById('leaflet-css')) {
      const link = document.createElement('link');
      link.id = 'leaflet-css';
      link.rel = 'stylesheet';
      link.href = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.css';
      document.head.appendChild(link);
    }

    function initMap() {
      if (!mapContainerRef.current || mapRef.current) return;
      const L = (window as any).L;
      if (!L) return;
      const map = L.map(mapContainerRef.current, {
        center: [5.3484, -4.0107],
        zoom: 12,
        zoomControl: true,
      });
      L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '\u00a9 OpenStreetMap',
        maxZoom: 19,
      }).addTo(map);
      mapRef.current = map;
    }

    if ((window as any).L) {
      initMap();
    } else {
      const script = document.createElement('script');
      script.id = 'leaflet-js';
      script.src = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.js';
      script.onload = () => initMap();
      document.head.appendChild(script);
    }
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    const L = (window as any).L;
    if (!map || !L) return;

    markersRef.current.forEach((m: any) => m.remove());
    markersRef.current = [];

    incidents.forEach((incident) => {
      const color = INCIDENT_COLORS[incident.incident_type];
      const emoji =
        incident.incident_type === 'panic' ? '\uD83D\uDEA8' :
        incident.incident_type === 'fire' ? '\uD83D\uDD25' :
        incident.incident_type === 'flood' ? '\uD83D\uDCA7' :
        incident.incident_type === 'medical' ? '\uD83C\uDFE5' : '\u26A0';

      const icon = L.divIcon({
        html: `<div style="width:28px;height:28px;border-radius:50%;background:${color};border:3px solid white;box-shadow:0 2px 8px rgba(0,0,0,0.4);display:flex;align-items:center;justify-content:center;font-size:13px">${emoji}</div>`,
        iconSize: [28, 28],
        iconAnchor: [14, 14],
        className: '',
      });

      const timeStr = new Date(incident.created_at).toLocaleTimeString('fr-CI', {
        hour: '2-digit',
        minute: '2-digit',
      });
      const isOpen = incident.status === 'open';

      const marker = L.marker([incident.location_lat, incident.location_lon], { icon })
        .bindPopup(
          `<div style="font-family:sans-serif;min-width:180px;color:#1e293b">
            <div style="font-weight:bold;font-size:14px;margin-bottom:4px">${emoji} ${incident.location_name || 'Alerte'}</div>
            <div style="color:#475569;font-size:12px;margin-bottom:6px">${incident.commune || 'Abidjan'}</div>
            ${incident.description ? `<div style="font-size:12px;margin-bottom:6px">${incident.description}</div>` : ''}
            <span style="padding:2px 8px;border-radius:9999px;font-size:11px;font-weight:600;background:${isOpen ? '#FEE2E2' : '#D1FAE5'};color:${isOpen ? '#DC2626' : '#059669'}">${isOpen ? 'Ouvert' : 'R\u00e9solu'}</span>
            <span style="color:#94a3b8;font-size:11px;margin-left:6px">${timeStr}</span>
          </div>`
        )
        .addTo(map);

      markersRef.current.push(marker);
    });
  }, [incidents]);

  return <div ref={mapContainerRef} className="w-full h-full" />;
}
