interface HeaderProps {
  health: any;
  wsConnected: boolean;
  mesh: any;
  onOpenSettings: () => void;
}

export function Header({ health, wsConnected, mesh, onOpenSettings }: HeaderProps) {
  const backend = health?.backend || '...';
  const version = health?.version || '...';
  const meshRole = mesh?.enabled ? (mesh?.role || '...') : 'OFF';

  return (
    <header className="border-b border-eidos-border bg-eidos-surface px-4 py-3">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div className="flex items-center gap-3">
          <span className="text-2xl">🧠</span>
          <div>
            <h1 className="text-lg font-bold text-eidos-text">EIDOS</h1>
            <p className="text-xs text-eidos-muted">
              Entidad Cognitiva Autónoma · v{version}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2 text-xs">
          <span className={`badge ${wsConnected ? 'bg-eidos-primary text-black' : 'bg-eidos-danger text-white'}`}>
            {wsConnected ? '● WS' : '○ WS'}
          </span>
          <span className="badge bg-eidos-border text-eidos-text">
            Backend: {backend}
          </span>
          <span className={`badge ${mesh?.enabled ? 'bg-eidos-accent text-black' : 'bg-eidos-muted text-eidos-text'}`}>
            MESH: {meshRole}
          </span>
          {/* Botón Settings (Fase 6) */}
          <button
            onClick={onOpenSettings}
            className="btn-secondary text-sm ml-2"
            title="Configuración: API keys, Cerebro Local"
          >
            ⚙️ Settings
          </button>
        </div>
      </div>
    </header>
  );
}
