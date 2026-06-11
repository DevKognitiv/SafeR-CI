'use client';

import { AuroraShell, BottomNav, GlassCard, TopBar } from '../_lib/shell';
import { useI18n, useStore, useTokens } from '../_lib/providers';
import { accentOf } from '../_lib/data';
import { DomainIcon } from '../_lib/icons';

export default function AuroraActivityPage() {
  const { t: tr } = useI18n();
  const { activity } = useStore();
  const t = useTokens();
  return (
    <AuroraShell>
      <TopBar back={{ href: '/aurora', label: tr('activity.back') }} />
      <h1 className="mt-7 text-[28px] font-semibold tracking-tight"
          style={{ fontFamily: '"Space Grotesk", Inter, sans-serif' }}>
        {tr('activity.full')}
      </h1>
      <div className="text-[12px] mt-1" style={{ color: t.textFaint }}>
        {tr('activity.lastMin', { n: activity.length })}
      </div>

      <GlassCard className="mt-6 p-5">
        {activity.length === 0 ? (
          <div className="text-[13px] text-center py-8" style={{ color: t.textSubtle }}>
            {tr('activity.empty')}
          </div>
        ) : (
          <ul className="divide-y" style={{ borderColor: t.glassBorder }}>
            {activity.map(ev => {
              const c = accentOf(ev.domain);
              return (
                <li key={ev.id} className="flex items-center gap-3 py-3 first:pt-0 last:pb-0"
                    style={{ borderColor: t.glassBorder }}>
                  <span className="h-9 w-9 rounded-xl grid place-items-center"
                        style={{ background: `${c}22`, border: `1px solid ${c}44` }}>
                    <DomainIcon name={ev.domain} size={18} color={c} />
                  </span>
                  <div className="flex-1 min-w-0">
                    <div className="text-[14px] truncate">{ev.entityName}</div>
                    <div className="text-[12px]" style={{ color: t.textSubtle }}>{ev.message}</div>
                  </div>
                  <div className="text-[11px] tabular-nums" style={{ color: t.textFaint }}>
                    {formatTs(ev.ts)}
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </GlassCard>

      <BottomNav current="activity" />
    </AuroraShell>
  );
}

function formatTs(ts: number): string {
  const diff = Date.now() - ts;
  if (diff < 60_000) return 'just now';
  if (diff < 3600_000) return `${Math.round(diff / 60_000)}m`;
  if (diff < 86_400_000) return `${Math.round(diff / 3600_000)}h`;
  return new Date(ts).toLocaleTimeString();
}
