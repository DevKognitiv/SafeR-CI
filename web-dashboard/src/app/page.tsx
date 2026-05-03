'use client';

import { useState, useEffect, useCallback } from 'react';
import dynamic from 'next/dynamic';
import { Shield, AlertTriangle, Activity, CheckCircle, Flame, Droplets, Phone, RefreshCw } from 'lucide-react';
import { Incident, INCIDENT_LABELS, INCIDENT_COLORS } from '@/types/incident';
import { timeAgo, getStats } from '@/lib/mock-data';
import SOSButton from '@/components/SOSButton';
import StatCard from '@/components/StatCard';
import AlertFeed from '@/components/AlertFeed';

// Dynamic import for map (no SSR - leaflet needs window)
const IncidentMap = dynamic(() => import('@/components/IncidentMap'), { 
  ssr: false,
  loading: () => (
    <div className="w-full h-full bg-slate-800 flex items-center justify-center rounded-xl">
      <div className="text-slate-400 text-sm">Chargement de la carte...</div>
    </div>
  )
});

export default function Dashboard() {
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [loading, setLoading] = useState(true);
  const [sosSending, setSosSending] = useState(false);
  const [sosSuccess, setSosSuccess] = useState(false);
  const [activeFilter, setActiveFilter] = useState<string>('all');
  const [lastRefresh, setLastRefresh] = useState<Date>(new Date());

  const fetchIncidents = useCallback(async () => {
    try {
      const url = activeFilter === 'all' 
        ? '/api/incidents' 
        : `/api/incidents?status=${activeFilter}`;
      const res = await fetch(url);
      const data = await res.json();
      setIncidents(data);
    } catch (e) {
      console.error('Failed to fetch incidents', e);
    } finally {
      setLoading(false);
      setLastRefresh(new Date());
    }
  }, [activeFilter]);

  useEffect(() => {
    fetchIncidents();
    const interval = setInterval(fetchIncidents, 30000);
    return () => clearInterval(interval);
  }, [fetchIncidents]);

  const handleSOS = async () => {
    if (sosSending || sosSuccess) return;
    setSosSending(true);

    try {
      let lat = 5.3600, lon = -4.0083;
      if (navigator.geolocation) {
        await new Promise<void>((resolve) => {
          navigator.geolocation.getCurrentPosition(
            (pos) => { lat = pos.coords.latitude; lon = pos.coords.longitude; resolve(); },
            () => resolve(),
            { timeout: 5000 }
          );
        });
      }

      await fetch('/api/incidents', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          incident_type: 'panic',
          severity: 'critical',
          location_lat: lat,
          location_lon: lon,
          location_name: 'Position GPS',
          source: 'web_dashboard',
          description: 'Alerte SOS depuis le tableau de bord web SafeR CI'
        })
      });

      setSosSuccess(true);
      await fetchIncidents();
      setTimeout(() => setSosSuccess(false), 8000);
    } catch (e) {
      console.error('SOS failed', e);
    } finally {
      setSosSending(false);
    }
  };

  const stats = getStats(incidents);
  const openIncidents = incidents.filter(i => i.status !== 'resolved');

  return (
    <div className="min-h-screen bg-slate-950 text-white">
      {/* Header */}
      <header className="border-b border-slate-800 px-6 py-4">
        <div className="max-w-7xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 bg-blue-600 rounded-lg flex items-center justify-center">
              <Shield className="w-5 h-5" />
            </div>
            <div>
              <h1 className="font-bold text-lg tracking-tight">SafeR CI</h1>
              <p className="text-xs text-slate-400">Tableau de bord sécurité — Côte d'Ivoire</p>
            </div>
          </div>
          <div className="flex items-center gap-4">
            <span className="flex items-center gap-1.5 text-xs text-slate-400">
              <span className="w-2 h-2 rounded-full bg-green-400 animate-pulse" />
              Système actif
            </span>
            <button
              onClick={fetchIncidents}
              className="p-2 rounded-lg hover:bg-slate-800 text-slate-400 hover:text-white transition-colors"
            >
              <RefreshCw className="w-4 h-4" />
            </button>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-6 py-6">
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          
          {/* Left column: SOS + Stats + Alert Feed */}
          <div className="space-y-5">
            {/* SOS Button */}
            <div className="bg-slate-900 rounded-2xl p-6 border border-slate-800 text-center">
              <p className="text-slate-400 text-sm mb-5 font-medium uppercase tracking-widest">
                Alerte d'urgence
              </p>
              <SOSButton 
                onPress={handleSOS} 
                isLoading={sosSending} 
                isSuccess={sosSuccess} 
              />
              {sosSuccess && (
                <p className="mt-4 text-green-400 text-sm font-medium animate-pulse">
                  ✅ Alerte envoyée aux secours!
                </p>
              )}
              {/* Emergency numbers */}
              <div className="mt-6 pt-5 border-t border-slate-800 grid grid-cols-3 gap-2">
                {[
                  { num: '170', label: 'Police', icon: '👮' },
                  { num: '180', label: 'Pompiers', icon: '🚒' },
                  { num: '185', label: 'SAMU', icon: '🏥' },
                ].map(({ num, label, icon }) => (
                  <a key={num} href={`tel:${num}`} className="flex flex-col items-center gap-1 p-2 rounded-lg hover:bg-slate-800 transition-colors cursor-pointer">
                    <span className="text-lg">{icon}</span>
                    <span className="text-white font-bold text-sm">{num}</span>
                    <span className="text-slate-500 text-xs">{label}</span>
                  </a>
                ))}
              </div>
            </div>

            {/* Stats */}
            <div className="grid grid-cols-2 gap-3">
              <StatCard label="Actifs" value={stats.open} color="red" icon={<AlertTriangle className="w-4 h-4" />} />
              <StatCard label="Critiques" value={stats.critical} color="orange" icon={<Flame className="w-4 h-4" />} />
              <StatCard label="En cours" value={stats.responding} color="blue" icon={<Activity className="w-4 h-4" />} />
              <StatCard label="Résolus" value={stats.resolved} color="green" icon={<CheckCircle className="w-4 h-4" />} />
            </div>

            {/* Alert Feed */}
            <AlertFeed incidents={incidents} loading={loading} />
          </div>

          {/* Right column: Map */}
          <div className="lg:col-span-2">
            <div className="bg-slate-900 rounded-2xl border border-slate-800 overflow-hidden h-[600px] lg:h-full min-h-[500px]">
              <div className="px-5 py-4 border-b border-slate-800 flex items-center justify-between">
                <h2 className="font-semibold text-sm">Carte des incidents — Grand Abidjan</h2>
                <div className="flex gap-2">
                  {['all','open','resolved'].map(f => (
                    <button 
                      key={f}
                      onClick={() => setActiveFilter(f)}
                      className={`px-3 py-1 rounded-full text-xs font-medium transition-colors ${
                        activeFilter === f 
                          ? 'bg-blue-600 text-white' 
                          : 'bg-slate-800 text-slate-400 hover:text-white'
                      }`}
                    >
                      {f === 'all' ? 'Tous' : f === 'open' ? 'Ouverts' : 'Résolus'}
                    </button>
                  ))}
                </div>
              </div>
              <div className="h-[calc(100%-57px)]">
                <IncidentMap incidents={openIncidents} />
              </div>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="mt-8 pt-5 border-t border-slate-800 flex items-center justify-between text-xs text-slate-600">
          <span>SafeR CI — Open-source safety platform for Côte d'Ivoire</span>
          <span>Mis à jour: {lastRefresh.toLocaleTimeString('fr-CI')}</span>
        </div>
      </main>
    </div>
  );
}
