'use client';

import * as React from 'react';
import { AreaSection, ActivityStrip, EntitySheet, HomePulse, StatusChips, useGrouped } from './_lib/widgets';
import { AuroraShell, BottomNav, TopBar } from './_lib/shell';
import { AREA_KEYS } from './_lib/data';
import { useStore } from './_lib/providers';

const TEMP = { value: 21.4, unit: '°C' };
const HUM = { value: 47, unit: '%' };
const PEOPLE = [
  { name: 'Amara', state: 'home' },
  { name: 'Yann', state: 'away' },
];

export default function AuroraDashboard() {
  const grouped = useGrouped();
  const { entities } = useStore();
  const [openId, setOpenId] = React.useState<string | null>(null);

  const all = Object.values(entities);
  const active = all.filter(e => e.isOn).length;
  const lightsOn = all.filter(e => e.domain === 'light' && e.isOn).length;
  const populated = AREA_KEYS.filter(k => grouped[k].length > 0);
  const peopleHome = PEOPLE.filter(p => p.state === 'home').length;

  return (
    <AuroraShell>
      <TopBar />
      <HomePulse activeCount={active} lightsOn={lightsOn}
                 areasCount={populated.length} peopleHome={peopleHome}
                 peopleTotal={PEOPLE.length} temp={TEMP} hum={HUM} />
      <StatusChips temp={TEMP} hum={HUM} people={PEOPLE} />

      <div className="mt-10 space-y-9">
        {populated.map(k => (
          <AreaSection key={k} areaKey={k} entities={grouped[k]} onEntity={setOpenId} />
        ))}
      </div>

      <ActivityStrip />
      <BottomNav current="dashboard" />

      <EntitySheet entityId={openId} onClose={() => setOpenId(null)} />
    </AuroraShell>
  );
}
