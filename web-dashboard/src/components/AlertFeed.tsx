import { Incident, INCIDENT_LABELS, INCIDENT_COLORS } from '@/types/incident';
import { timeAgo } from '@/lib/mock-data';

const STATUS_BADGES: Record<string, string> = {
  open: 'bg-red-500/20 text-red-400',
  acknowledged: 'bg-yellow-500/20 text-yellow-400',
  responding: 'bg-blue-500/20 text-blue-400',
  resolved: 'bg-green-500/20 text-green-400',
};

const STATUS_LABELS: Record<string, string> = {
  open: 'Ouvert',
  acknowledged: 'Reçu',
  responding: 'En cours',
  resolved: 'Résolu',
};

interface AlertFeedProps {
  incidents: Incident[];
  loading: boolean;
}

export default function AlertFeed({ incidents, loading }: AlertFeedProps) {
  const recent = incidents.slice(0, 8);

  return (
    <div className="bg-slate-900 rounded-2xl border border-slate-800">
      <div className="px-5 py-4 border-b border-slate-800">
        <h2 className="font-semibold text-sm">Dernières alertes</h2>
      </div>
      <div className="divide-y divide-slate-800 max-h-80 overflow-y-auto">
        {loading ? (
          Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="px-5 py-4 animate-pulse">
              <div className="h-3 bg-slate-800 rounded w-3/4 mb-2" />
              <div className="h-2.5 bg-slate-800 rounded w-1/2" />
            </div>
          ))
        ) : recent.length === 0 ? (
          <div className="px-5 py-8 text-center text-slate-500 text-sm">
            Aucun incident récent
          </div>
        ) : (
          recent.map((incident) => (
            <div key={incident.id} className="px-5 py-3.5 hover:bg-slate-800/50 transition-colors">
              <div className="flex items-start justify-between gap-2">
                <div className="flex items-center gap-2 min-w-0">
                  <span 
                    className="w-2.5 h-2.5 rounded-full flex-shrink-0 mt-0.5"
                    style={{ backgroundColor: INCIDENT_COLORS[incident.incident_type] }}
                  />
                  <div className="min-w-0">
                    <div className="text-sm font-medium truncate">
                      {INCIDENT_LABELS[incident.incident_type]}
                    </div>
                    <div className="text-xs text-slate-400 truncate">
                      {incident.location_name || incident.commune || 'Position inconnue'}
                    </div>
                  </div>
                </div>
                <div className="flex flex-col items-end gap-1 flex-shrink-0">
                  <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${STATUS_BADGES[incident.status]}`}>
                    {STATUS_LABELS[incident.status]}
                  </span>
                  <span className="text-xs text-slate-500">{timeAgo(incident.created_at)}</span>
                </div>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
