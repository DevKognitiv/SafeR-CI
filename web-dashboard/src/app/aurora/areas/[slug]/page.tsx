'use client';

import * as React from 'react';
import { useParams } from 'next/navigation';
import { AuroraShell, BottomNav, TopBar } from '../../_lib/shell';
import { EntitySheet, EntityTile, useGrouped } from '../../_lib/widgets';
import { useI18n, useTokens } from '../../_lib/providers';
import { AREA_KEYS, isAreaKey } from '../../_lib/data';

export default function AreaPage() {
  const { t: tr } = useI18n();
  const params = useParams<{ slug: string }>();
  const slug = (params?.slug as string) ?? '';
  const grouped = useGrouped();
  const t = useTokens();
  const [openId, setOpenId] = React.useState<string | null>(null);

  if (!isAreaKey(slug)) {
    return (
      <AuroraShell>
        <TopBar back={{ href: '/aurora', label: tr('activity.back') }} />
        <div className="mt-10 text-center" style={{ color: t.textSubtle }}>
          Area not found. Choose one of: {AREA_KEYS.map(k => tr(`area.${k}`)).join(', ')}.
        </div>
        <BottomNav current="dashboard" />
      </AuroraShell>
    );
  }

  const entities = grouped[slug];

  return (
    <AuroraShell>
      <TopBar back={{ href: '/aurora', label: tr('activity.back') }} />
      <h1 className="mt-7 text-[28px] font-semibold tracking-tight"
          style={{ fontFamily: '"Space Grotesk", Inter, sans-serif' }}>
        {tr(`area.${slug}`)}
      </h1>
      <div className="text-[12px] mt-1" style={{ color: t.textFaint }}>
        {entities.filter(e => e.isOn).length} {tr('area.active')} · {entities.length} {tr('area.devices')}
      </div>

      <div className="mt-6 grid grid-cols-2 md:grid-cols-3 gap-3">
        {entities.map(e => <EntityTile key={e.id} entity={e} onClick={() => setOpenId(e.id)} />)}
      </div>

      <BottomNav current="dashboard" />
      <EntitySheet entityId={openId} onClose={() => setOpenId(null)} />
    </AuroraShell>
  );
}
