import { EvolutionStats } from '../hooks/useEidosApi';

interface EvolutionPanelProps {
  evolution: EvolutionStats | null;
}

export function EvolutionPanel({ evolution }: EvolutionPanelProps) {
  if (!evolution) {
    return (
      <div className="panel p-4">
        <span className="text-sm font-bold">⚡ Evolution</span>
        <p className="text-xs text-eidos-muted mt-1">Cargando...</p>
      </div>
    );
  }

  return (
    <div className="panel p-4">
      <div className="flex items-center gap-2 mb-3">
        <span className="text-sm font-bold">⚡ Autoevolución</span>
        <span className={`badge ${evolution.auto_forge_enabled ? 'bg-eidos-primary text-black' : 'bg-eidos-muted text-eidos-text'}`}>
          {evolution.auto_forge_enabled ? 'AUTO' : 'MANUAL'}
        </span>
      </div>

      <div className="grid grid-cols-2 gap-2 text-sm">
        <div className="bg-eidos-bg border border-eidos-border rounded p-2">
          <p className="text-xs text-eidos-muted">Total cápsulas</p>
          <p className="text-lg font-bold text-eidos-text">{evolution.total_capsules}</p>
        </div>
        <div className="bg-eidos-bg border border-eidos-border rounded p-2">
          <p className="text-xs text-eidos-muted">Favoritas ★</p>
          <p className="text-lg font-bold text-eidos-primary">{evolution.favorites}</p>
        </div>
        <div className="bg-eidos-bg border border-eidos-border rounded p-2">
          <p className="text-xs text-eidos-muted">Promociones</p>
          <p className="text-lg font-bold text-eidos-warning">{evolution.promotion_candidates}</p>
        </div>
        <div className="bg-eidos-bg border border-eidos-border rounded p-2">
          <p className="text-xs text-eidos-muted">Threshold</p>
          <p className="text-lg font-bold text-eidos-text">
            {evolution.promotion_threshold}<span className="text-xs text-eidos-muted">/{evolution.promotion_window_hours}h</span>
          </p>
        </div>
      </div>
    </div>
  );
}
