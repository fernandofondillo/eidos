import { MeshStatus } from '../hooks/useEidosApi';

interface MeshMapProps {
  mesh: MeshStatus | null;
}

export function MeshMap({ mesh }: MeshMapProps) {
  if (!mesh) {
    return (
      <div className="panel p-4">
        <span className="text-sm font-bold">🌐 MESH</span>
        <p className="text-xs text-eidos-muted mt-1">Cargando...</p>
      </div>
    );
  }

  if (!mesh.enabled) {
    return (
      <div className="panel p-4">
        <div className="flex items-center gap-2 mb-2">
          <span className="text-sm font-bold">🌐 MESH</span>
          <span className="badge bg-eidos-muted text-eidos-text">OFF</span>
        </div>
        <p className="text-xs text-eidos-muted">
          Activa el MESH en config/eidos.yaml para correr en enjambre.
        </p>
      </div>
    );
  }

  const isLeader = mesh.role === 'leader';
  const roleColor = isLeader ? 'text-eidos-primary' : 'text-eidos-accent';
  const roleIcon = isLeader ? '👑' : '🔧';

  return (
    <div className="panel p-4">
      <div className="flex items-center gap-2 mb-3">
        <span className="text-sm font-bold">🌐 MESH Status</span>
        <span className={`badge ${isLeader ? 'bg-eidos-primary text-black' : 'bg-eidos-accent text-black'}`}>
          {mesh.role?.toUpperCase()}
        </span>
      </div>

      <div className="space-y-2 text-sm">
        <div className="flex justify-between">
          <span className="text-eidos-muted text-xs">Node ID:</span>
          <span className="font-mono text-xs">{mesh.node_id?.slice(0, 12)}...</span>
        </div>
        <div className="flex justify-between">
          <span className="text-eidos-muted text-xs">Leader:</span>
          <span className="font-mono text-xs">
            {mesh.leader_id ? mesh.leader_id.slice(0, 12) + '...' : 'none'}
          </span>
        </div>
        <div className="flex justify-between">
          <span className="text-eidos-muted text-xs">Peers:</span>
          <span className="text-eidos-text">{mesh.peers || 0}</span>
        </div>

        {/* Visualización simple de topología */}
        <div className="mt-3 p-3 bg-eidos-bg border border-eidos-border rounded flex items-center justify-center gap-4">
          <div className="text-center">
            <div className="text-2xl">{roleIcon}</div>
            <div className={`text-xs ${roleColor} font-bold`}>
              {isLeader ? 'LEADER' : 'WORKER'}
            </div>
            <div className="text-xs text-eidos-muted">you</div>
          </div>
          {!isLeader && (
            <>
              <div className="text-eidos-muted">←→</div>
              <div className="text-center">
                <div className="text-2xl">👑</div>
                <div className="text-xs text-eidos-primary font-bold">LEADER</div>
                <div className="text-xs text-eidos-muted">remote</div>
              </div>
            </>
          )}
          {isLeader && (mesh.peers || 0) > 0 && (
            <>
              <div className="text-eidos-muted">←→</div>
              <div className="text-center">
                <div className="text-2xl">🔧</div>
                <div className="text-xs text-eidos-accent font-bold">{mesh.peers}</div>
                <div className="text-xs text-eidos-muted">workers</div>
              </div>
            </>
          )}
        </div>

        {mesh.arbitrator && (
          <div className="mt-2">
            <p className="text-xs text-eidos-muted mb-1">Tokens activos:</p>
            {Object.entries(mesh.arbitrator.by_resource || {}).length > 0 ? (
              <div className="flex flex-wrap gap-1">
                {Object.entries(mesh.arbitrator.by_resource).map(([res, count]) => (
                  <span key={res} className="badge bg-eidos-warning text-black">
                    {res}: {count as number}
                  </span>
                ))}
              </div>
            ) : (
              <p className="text-xs text-eidos-muted">Sin tokens activos.</p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
