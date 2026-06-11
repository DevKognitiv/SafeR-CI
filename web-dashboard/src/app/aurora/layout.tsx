import { AuroraProviders } from './_lib/providers';

export default function AuroraLayout({ children }: { children: React.ReactNode }) {
  return <AuroraProviders>{children}</AuroraProviders>;
}
