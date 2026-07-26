import { useState } from 'react';
import { CapsulesData } from '../hooks/useEidosApi';

interface CapsulesManagerProps {
  capsules: CapsulesData | null;
  onForge: (request: string, forcePending: boolean) => Promise<any>;
  onApprove: (draftId: string) => Promise<any>;
  onReject: (draftId: string) => Promise<any>;
  onRefresh: () => void;
}

export function CapsulesManager({ capsules, onForge, onApprove, onReject, onRefresh }: CapsulesManagerProps) {
  const [forgeInput, setForgeInput] = useState('');
  const [forging, setForging] = useState(false);

  const handleForge = async (e: React.FormEvent) => {
    e.preventDefault();
    if (forgeInput.trim() && !forging) {
      setForging(true);
      try {
        await onForge(forgeInput.trim(), false);
        setForgeInput('');
        onRefresh();
      } catch (err) {
        console.error('Forge error:', err);
      } finally {
        setForging(false);
      }
    }
  };

  const handleApprove = async (id: string) => {
    await onApprove(id);
    onRefresh();
  };

  const handleReject = async (id: string) => {
    await onReject(id);
    onRefresh();
  };

  return (
    <div className="panel p-4">
      <div className="flex items-center gap-2 mb-3">
        <span className="text-sm font-bold">🧬 Cápsulas</span>
        <span className="text-xs text-eidos-muted">
          — {capsules?.drafts.length || 0} drafts · {capsules?.active.length || 0} activas
        </span>
      </div>

      <form onSubmit={handleForge} className="mb-3 flex gap-2">
        <input
          type="text"
          value={forgeInput}
          onChange={e => setForgeInput(e.target.value)}
          placeholder="Forjar: experto en..."
          className="input flex-1 text-sm"
          disabled={forging}
        />
        <button type="submit" className="btn-primary text-sm" disabled={forging || !forgeInput.trim()}>
          Forjar
        </button>
      </form>

      {capsules?.drafts && capsules.drafts.length > 0 && (
        <div className="mb-3">
          <p className="text-xs text-eidos-muted mb-1">Drafts pendientes:</p>
          <div className="space-y-1 max-h-32 overflow-y-auto">
            {capsules.drafts.map(d => (
              <div key={d.id} className="flex items-center justify-between bg-eidos-bg border border-eidos-border rounded p-2 text-xs">
                <div className="flex-1 min-w-0">
                  <span className="font-medium">{d.name}</span>
                  <span className="text-eidos-muted ml-2">
                    conf: {(d.genesis_confidence * 100).toFixed(0)}%
                  </span>
                </div>
                {d.status === 'pending' && (
                  <div className="flex gap-1">
                    <button onClick={() => handleApprove(d.id)} className="btn-primary text-xs px-2 py-0.5">
                      ✓
                    </button>
                    <button onClick={() => handleReject(d.id)} className="btn-danger text-xs px-2 py-0.5">
                      ✗
                    </button>
                  </div>
                )}
                {d.status !== 'pending' && (
                  <span className="badge bg-eidos-border text-eidos-muted">{d.status}</span>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {capsules?.active && capsules.active.length > 0 && (
        <div>
          <p className="text-xs text-eidos-muted mb-1">Cápsulas activas:</p>
          <div className="space-y-1 max-h-32 overflow-y-auto">
            {capsules.active.map(c => (
              <div key={c.id} className="flex items-center justify-between bg-eidos-bg border border-eidos-border rounded p-2 text-xs">
                <div className="flex-1 min-w-0">
                  <span className="font-medium">
                    {c.favorite && '★ '}{c.name}
                  </span>
                  <span className="text-eidos-muted ml-2">
                    uses: {c.uses} · TTL: {c.ttl_days}d
                  </span>
                </div>
                <span className="badge bg-eidos-border text-eidos-muted">{c.version}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {!capsules?.drafts?.length && !capsules?.active?.length && (
        <p className="text-xs text-eidos-muted">No hay cápsulas. Forja una arriba.</p>
      )}
    </div>
  );
}
