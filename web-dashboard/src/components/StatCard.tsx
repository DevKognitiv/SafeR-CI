interface StatCardProps {
  label: string;
  value: number;
  color: 'red' | 'orange' | 'blue' | 'green';
  icon: React.ReactNode;
}

const colorMap = {
  red: 'text-red-400 bg-red-500/10 border-red-500/20',
  orange: 'text-orange-400 bg-orange-500/10 border-orange-500/20',
  blue: 'text-blue-400 bg-blue-500/10 border-blue-500/20',
  green: 'text-green-400 bg-green-500/10 border-green-500/20',
};

export default function StatCard({ label, value, color, icon }: StatCardProps) {
  return (
    <div className={`rounded-xl p-4 border ${colorMap[color]}`}>
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs font-medium opacity-80 uppercase tracking-wide">{label}</span>
        {icon}
      </div>
      <div className="text-3xl font-bold">{value}</div>
    </div>
  );
}
