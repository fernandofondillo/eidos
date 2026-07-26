import { MotivationStats } from '../hooks/useEidosApi';

interface RewardChartProps {
  motivation: MotivationStats | null;
}

export function RewardChart({ motivation }: RewardChartProps) {
  if (!motivation) {
    return (
      <div className="panel p-4">
        <span className="text-sm font-bold">🎯 Reward Signal</span>
        <p className="text-xs text-eidos-muted mt-1">Cargando...</p>
      </div>
    );
  }

  const total = motivation.session_total_reward;
  const totalColor = total >= 0 ? 'text-eidos-primary' : 'text-eidos-danger';

  const drivers = [
    { name: 'curiosity', label: 'Curiosidad', icon: '🔍', color: 'bg-eidos-accent' },
    { name: 'capsule_reuse', label: 'Cápsulas', icon: '🧬', color: 'bg-eidos-primary' },
    { name: 'user_satisfaction', label: 'Satisfac.', icon: '😊', color: 'bg-eidos-warning' },
  ];

  return (
    <div className="panel p-4">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <span className="text-sm font-bold">🎯 Reward Signal</span>
        </div>
        <div className="text-right">
          <span className={`text-lg font-bold ${totalColor}`}>
            {total >= 0 ? '+' : ''}{total.toFixed(3)}
          </span>
          <p className="text-xs text-eidos-muted">total sesión</p>
        </div>
      </div>

      <div className="space-y-2">
        {drivers.map(d => {
          const data = motivation.by_driver[d.name];
          const count = data?.count || 0;
          const delta = data?.total_delta || 0;
          const deltaColor = delta >= 0 ? 'text-eidos-primary' : 'text-eidos-danger';
          return (
            <div key={d.name} className="flex items-center justify-between text-sm">
              <span className="flex items-center gap-2">
                <span>{d.icon}</span>
                <span className="text-eidos-text text-xs">{d.label}</span>
              </span>
              <span className="text-xs">
                <span className="text-eidos-muted">{count}×</span>{' '}
                <span className={deltaColor}>
                  {delta >= 0 ? '+' : ''}{delta.toFixed(3)}
                </span>
              </span>
            </div>
          );
        })}
      </div>

      <div className="mt-3 pt-2 border-t border-eidos-border flex items-center justify-between text-xs">
        <span className="text-eidos-muted">
          Streak: {motivation.satisfaction_streak}/{motivation.satisfaction_window}
        </span>
        <span className="text-eidos-muted">
          Window: {motivation.confidence_window_size}
        </span>
      </div>

      {/* Mini timeline de rewards recientes */}
      {motivation.recent_rewards && motivation.recent_rewards.length > 0 && (
        <div className="mt-3">
          <p className="text-xs text-eidos-muted mb-1">Recientes:</p>
          <div className="flex items-end gap-0.5 h-8">
            {motivation.recent_rewards.slice(0, 20).reverse().map((r, i) => {
              const delta = r.delta || 0;
              const height = Math.min(100, Math.abs(delta) * 100);
              const color = delta >= 0 ? 'bg-eidos-primary' : 'bg-eidos-danger';
              return (
                <div
                  key={i}
                  className={`flex-1 ${color} rounded-t`}
                  style={{ height: `${Math.max(10, height)}%` }}
                  title={`${r.driver}: ${delta}`}
                />
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
