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
  const mapReadyRef = useRef<boolean>(false);

  useEffect(() => {
    if (typeof window === 'undefined' || mapReadyRef.current) return;

    // Dynamically load Leaflet CSS
    if (!document.getElementById('leaflet-css')) {
      const link = document.createElement('link');
      link.id = 'leaflet-css';
      link.rel = 'stylesheet';
      link.href = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.css';
      document.head.appendChild(link);
    }

    // Dynamically load Leaflet JS
    const existingScript = document.getElementById('leaflet-js');
    if (existingScript) {
      // Leaflet already loaded
      initMap();
      return;
    }
    
    const script = document.createElement('script');
    script.id = 'leaflet-js';
    script.src = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.js';
    script.onload = () => initMap();
    document.head.appendChild(script);

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
        attribution: '© OpenStreetMap contributors',
        maxZoom: 19,
      }).addTo(map);

      mapRef.current = map;
      mapReadyRef.current = true;
    }
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    const L = (window as any).L;
    if (!map || typeof window === 'undefined' || !L) return;

    // Clear existing markers
    markersRef.current.forEach((m: any) => m.remove());
    markersRef.current = [];

    incidents.forEach((incident) => {
      const color = INCIDENT_COLORS[incident.incident_type];
      const emoji = incident.incident_type === 'panic' ? '🚨' :
          incident.incident_type === 'fire' ? '🔥' :
          incident.incident_type === 'flood' ? '💧' :
          incident.incident_type === 'medical' ? '🏥' : '⚠️';

      const icon = L.divIcon({
        html: `<div style="width:28px;height:28px;border-radius:50%;background:${color};border:3px solid white;box-shadow:0 2px 8px rgba(0,0,0,0.4);display:flex;align-items:center;justify-content:center;font-size:12px">${emoji}</div>`,
        iconSize: [28, 28],
        iconAnchor: [14, 14],
        className: '',
      });

      const timeStr = new Date(incident.created_at).toLocaleTimeString('fr-CI', { hour: '2-digit', minute: '2-digit' });
      const statusLabel = incident.status === 'open' ? 'Ouvert' : incident.status === 'resolved' ? 'Résolu' : 'En cours';
      const statusColor = incident.status === 'open' ? '#DC2626' : incident.status === 'resolved' ? '#059669' : '#2563EB';
      const statusBg = incident.status === 'open' ? '#FEE2E2' : incident.status === 'resolved' ? '#D1FAE5' : '#DBEAFE';

      const marker = L.marker([incident.location_lat, incident.location_lon], { icon })
        .bindPopup(`<div style="font-family:sans-serif;min-width:180px;color:#1e293b">
          <div style="font-weight:bold;font-size:14px;margin-bottom:4px">${emoji} ${incident.location_name || incident.commune || 'Alerte'}</div>
          <div style="color:#475569;font-size:12px;margin-bottom:6px">${incident.location_name || 'Position inconnue'}</div>
          ${incident.description ? `<div style="font-size:12px;margin-bottom:6px">${incident.description}</div>` : ''}
          <div style="display:flex;gap:6px;align-items:center">
            <span style="padding:2px 8px;border-radius:9999px;font-size:11px;font-weight:600;background:${statusBg};color:${statusColor}">${statusLabel}</span>
            <span style="color:#94a3b8;font-size:11px">${timeStr}</span>
          </div>
        </div>`)
        .addTo(map);

      markersRef.current.push(marker);
    });
  }, [incidents]);

  return <div ref={mapContainerRef} className="w-full h-full" />;
}
'use client';
import { useEffect, useRef } from 'react';
import { Incident, INCIDENT_COLORS } from '@/types/incident';

interface IncidentMapProps {
  incidents: Incident[];
}

declare global {
  interface Window {
    L: any;
  }
}

export default function IncidentMap({ incidents }: IncidentMapProps) {
  const mapRef = useRef<any>(null);
  const mapContainerRef = useRef<HTMLDivElement>(null);
  const markersRef = useRef<any[]>([]);

  useEffect(() => {
    if (typeof window === 'undefined' || mapRef.current) return;

    // Dynamically load Leaflet CSS
    if (!document.getElementById('leaflet-css')) {
      const link = document.createElement('link');
      link.id = 'leaflet-css';
      link.rel = 'stylesheet';
      link.href = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.css';
      document.head.appendChild(link);
    }

    // Dynamically load Leaflet JS
    const script = document.createElement('script');
    script.src = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.js';
    script.onload = () => {
      if (!mapContainerRef.current || mapRef.current) return;
      const L = window.L;

      const map = L.map(mapContainerRef.current, {
        center: [5.3484, -4.0107],
        zoom: 12,
        zoomControl: true,
      });

      L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '© OpenStreetMap contributors',
        maxZoom: 19,
      }).addTo(map);

      mapRef.current = map;
      window._saferMap = map;
    };
    document.head.appendChild(script);
  }, []);

  useEffect(() => {
    const map = mapRef.current || window._saferMap;
    if (!map || typeof window === 'undefined' || !window.L) return;

    const L = window.L;
    // Clear existing markers
    markersRef.current.forEach(m => m.remove());
    markersRef.current = [];

    incidents.forEach((incident) => {
      const color = INCIDENT_COLORS[incident.incident_type];
      const icon = L.divIcon({
        html: `<div style="
          width:28px; height:28px; border-radius:50%;
          background:${color}; border:3px solid white;
          box-shadow:0 2px 8px rgba(0,0,0,0.4);
          display:flex; align-items:center; justify-content:center;
          font-size:12px;
        ">${
          incident.incident_type === 'panic' ? '🚨' :
          incident.incident_type === 'fire' ? '🔥' :
          incident.incident_type === 'flood' ? '💧' :
          incident.incident_type === 'medical' ? '🏥' : '⚠️'
        }</div>`,
        iconSize: [28, 28],
        iconAnchor: [14, 14],
        className: '',
      });

      const timeStr = new Date(incident.created_at).toLocaleTimeString('fr-CI', { hour: '2-digit', minute: '2-digit' });
      const marker = L.marker([incident.location_lat, incident.location_lon], { icon })
        .bindPopup(`
          <div style="font-family:sans-serif;min-width:180px;color:#1e293b;">
            <div style="font-weight:bold;font-size:14px;margin-bottom:4px">
              ${incident.incident_type === 'panic' ? '🚨 Panique' :
                incident.incident_type === 'fire' ? '🔥 Incendie' :
                incident.incident_type === 'flood' ? '💧 Inondation' :
                incident.incident_type === 'medical' ? '🏥 Médical' : '⚠️ Autre'}
            </div>
            <div style="color:#475569;font-size:12px;margin-bottom:6px">
              📍 ${incident.location_name || incident.commune || 'Position inconnue'}
            </div>
            ${incident.description ? `<div style="font-size:12px;margin-bottom:6px;">${incident.description}</div>` : ''}
            <div style="display:flex;gap:6px;align-items:center;">
              <span style="padding:2px 8px;border-radius:9999px;font-size:11px;font-weight:600;background:${
                incident.status === 'open' ? '#FEE2E2' : 
                incident.status === 'resolved' ? '#D1FAE5' : '#DBEAFE'};color:${
                incident.status === 'open' ? '#DC2626' : 
                incident.status === 'resolved' ? '#059669' : '#2563EB'};">
                ${incident.status === 'open' ? 'Ouvert' : incident.status === 'resolved' ? 'Résolu' : 'En cours'}
              </span>
              <span style="color:#94a3b8;font-size:11px;">${timeStr}</span>
            </div>
          </div>
        `)
        .addTo(map);

      markersRef.current.push(marker);
    });
  }, [incidents]);

  return <div ref={mapContainerRef} className="w-full h-full" />;
}
