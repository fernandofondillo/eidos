import { MemoryStats } from '../hooks/useEidosApi';

interface MemoryStatsPanelProps {
  stats: MemoryStats | null;
}

export function MemoryStatsPanel({ stats }: MemoryStatsPanelProps) {
  if (!stats) {
    return (
      <div className="panel p-4">
        <span className="text-sm font-bold">🧩 Memoria (5 capas)</span>
        <p className="text-xs text-eidos-muted mt-1">Cargando...</p>
      </div>
    );
  }

  const layers = [
    { name: 'Sensorial', icon: '⚡', data: stats.sensory, keys: ['buffered', 'total_persisted'] },
    { name: 'Episódica', icon: '📚', data: stats.episodic, keys: ['total', 'vec_extension', 'embedding_dim'] },
    { name: 'Semántica', icon: '🕸️', data: stats.semantic, keys: ['nodes', 'edges'] },
    { name: 'Procedimental', icon: '⚙️', data: stats.procedural, keys: ['total', 'favorites', 'expired_pending'] },
    { name: 'Metacognitiva', icon: '🧭', data: stats.metacognitive, keys: ['total', 'avg_confidence'] },
  ];

  return (
    <div className="panel p-4">
      <div className="flex items-center gap-2 mb-3">
        <span className="text-sm font-bold">🧩 Memoria Cognitiva</span>
        <span className="text-xs text-eidos-muted">— 5 capas</span>
      </div>
      <div className="space-y-2">
        {layers.map(layer => (
          <div key={layer.name} className="flex items-center justify-between text-sm">
            <span className="flex items-center gap-2">
              <span>{layer.icon}</span>
              <span className="text-eidos-text">{layer.name}</span>
            </span>
            <span className="text-xs text-eidos-muted font-mono">
              {layer.keys.map(k => `${k}=${layer.data?.[k] ?? '?'}`).join(' · ')}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
