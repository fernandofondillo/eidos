import { Monologue } from '../hooks/useEidosApi';

interface MonologueViewerProps {
  monologue: Monologue | null;
}

export function MonologueViewer({ monologue }: MonologueViewerProps) {
  if (!monologue) {
    return (
      <div className="panel p-4">
        <div className="flex items-center gap-2 mb-2">
          <span className="text-sm font-bold">💭 Monólogo Interno</span>
        </div>
        <p className="text-sm text-eidos-muted">
          El monólogo estructurado de EIDOS aparecerá aquí cuando piense.
        </p>
      </div>
    );
  }

  const confColor = monologue.confidence >= 0.7 ? 'text-eidos-primary'
    : monologue.confidence >= 0.4 ? 'text-eidos-warning'
    : 'text-eidos-danger';

  return (
    <div className="panel p-4">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <span className="text-sm font-bold">💭 Monólogo Interno</span>
          <span className="text-xs text-eidos-muted">— pensamiento estructurado</span>
        </div>
        <span className="text-xs text-eidos-muted font-mono">
          {monologue.id.slice(0, 8)}
        </span>
      </div>

      <div className="space-y-2 text-sm">
        <div>
          <span className="text-eidos-muted text-xs">INPUT:</span>
          <p className="font-mono text-eidos-text">{monologue.input_summary}</p>
        </div>

        <div>
          <span className="text-eidos-muted text-xs">OBSERVATION:</span>
          <p className="text-eidos-text">{monologue.observation}</p>
        </div>

        <div>
          <span className="text-eidos-muted text-xs">HYPOTHESIS:</span>
          <p className="text-eidos-text">{monologue.hypothesis}</p>
        </div>

        <div>
          <span className="text-eidos-muted text-xs">PLAN ({monologue.plan.length} pasos):</span>
          <ol className="list-decimal list-inside text-eidos-text mt-1 space-y-0.5">
            {monologue.plan.map((step, i) => (
              <li key={i} className="text-sm">{step}</li>
            ))}
          </ol>
        </div>

        <div className="flex items-center gap-4 pt-2 border-t border-eidos-border">
          <div>
            <span className="text-eidos-muted text-xs">RISK:</span>{' '}
            <span className={monologue.risk === 'none' ? 'text-eidos-primary' : 'text-eidos-warning'}>
              {monologue.risk}
            </span>
          </div>
          <div>
            <span className="text-eidos-muted text-xs">CONFIDENCE:</span>{' '}
            <span className={confColor}>
              {(monologue.confidence * 100).toFixed(0)}%
            </span>
          </div>
          <div>
            <span className="text-eidos-muted text-xs">BACKEND:</span>{' '}
            <span className="text-eidos-accent">{monologue.backend}</span>
          </div>
        </div>
      </div>
    </div>
  );
}
