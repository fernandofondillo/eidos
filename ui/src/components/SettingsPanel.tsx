import { useState, useEffect, useCallback } from 'react';

interface Provider {
  id: string;
  name: string;
  env_var: string;
  api_type: string;
  base_url: string;
  default_model: string;
  docs_url: string;
  description: string;
}

interface KeyInfo {
  provider: string;
  env_var: string;
  set: boolean;
  preview: string;
}

interface DownloadStatus {
  active: boolean;
  model_id: string | null;
  received_bytes: number;
  total_bytes: number;
  error: string | null;
  completed: boolean;
  percent: number;
}

const API_BASE = '';

async function apiGet<T>(path: string): Promise<T> {
  const r = await fetch(`${API_BASE}${path}`);
  if (!r.ok) throw new Error(`${r.status}: ${await r.text()}`);
  return r.json();
}

async function apiPost<T>(path: string, body?: any): Promise<T> {
  const r = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!r.ok) throw new Error(`${r.status}: ${await r.text()}`);
  return r.json();
}

export function SettingsPanel({ onClose }: { onClose: () => void }) {
  const [providers, setProviders] = useState<Provider[]>([]);
  const [keys, setKeys] = useState<Record<string, KeyInfo>>({});
  const [inputValues, setInputValues] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<{ type: 'success' | 'error' | 'info'; text: string } | null>(null);

  // Estado de descarga del cerebro local
  const [models, setModels] = useState<any[]>([]);
  const [downloadStatus, setDownloadStatus] = useState<DownloadStatus | null>(null);
  const [downloading, setDownloading] = useState(false);

  const loadAll = useCallback(async () => {
    try {
      const [prov, keysResp] = await Promise.all([
        apiGet<{ providers: Provider[] }>('/api/providers'),
        apiGet<{ keys: Record<string, KeyInfo> }>('/api/config/keys'),
      ]);
      setProviders(prov.providers);
      setKeys(keysResp.keys);
    } catch (err) {
      setMessage({ type: 'error', text: `Error cargando: ${err}` });
    }
  }, []);

  const loadModels = useCallback(async () => {
    try {
      const resp = await apiGet<{ models: any[]; cortex_enabled: boolean }>('/api/models');
      setModels(resp.models);
    } catch {
      setModels([]);
    }
  }, []);

  useEffect(() => {
    loadAll();
    loadModels();
  }, [loadAll, loadModels]);

  // Polling del estado de descarga
  useEffect(() => {
    if (!downloading) return;
    const poll = setInterval(async () => {
      try {
        const status = await apiGet<DownloadStatus>('/api/models/download/status');
        setDownloadStatus(status);
        if (status.completed || status.error) {
          setDownloading(false);
          clearInterval(poll);
          loadModels();
          if (status.error) {
            setMessage({ type: 'error', text: `Error descarga: ${status.error}` });
          } else {
            setMessage({ type: 'success', text: 'Cerebro Local descargado correctamente.' });
          }
        }
      } catch {}
    }, 1000);
    return () => clearInterval(poll);
  }, [downloading, loadModels]);

  const handleSaveKey = async (envVar: string) => {
    const value = inputValues[envVar];
    if (!value?.trim()) {
      setMessage({ type: 'error', text: 'Pega una API key válida primero.' });
      return;
    }
    setSaving(true);
    try {
      await apiPost('/api/config/keys', { keys: { [envVar]: value.trim() } });
      setInputValues({ ...inputValues, [envVar]: '' });
      await loadAll();
      setMessage({ type: 'success', text: 'API key guardada. Se aplicará en caliente.' });
    } catch (err) {
      setMessage({ type: 'error', text: `Error guardando: ${err}` });
    } finally {
      setSaving(false);
    }
  };

  const handleClearKey = async (envVar: string) => {
    if (!confirm(`¿Borrar la API key de ${envVar}?`)) return;
    setSaving(true);
    try {
      await apiPost('/api/config/keys/clear', { env_var: envVar });
      await loadAll();
      setMessage({ type: 'info', text: 'API key borrada.' });
    } catch (err) {
      setMessage({ type: 'error', text: `Error borrando: ${err}` });
    } finally {
      setSaving(false);
    }
  };

  const handleDownloadBrain = async () => {
    setDownloading(true);
    setMessage({ type: 'info', text: 'Iniciando descarga del Cerebro Local (~2 GB)...' });
    try {
      // Registrar modelo si no existe
      await apiPost('/api/models/register', { model_id: 'qwen2.5-3b-instruct' });
      // Iniciar descarga
      await apiPost('/api/models/download', { model_id: 'qwen2.5-3b-instruct' });
    } catch (err) {
      setDownloading(false);
      setMessage({ type: 'error', text: `Error: ${err}` });
    }
  };

  const formatBytes = (b: number) => {
    if (b === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(b) / Math.log(k));
    return `${(b / Math.pow(k, i)).toFixed(1)} ${sizes[i]}`;
  };

  return (
    <div className="fixed inset-0 bg-black/70 z-50 flex items-center justify-center p-4">
      <div className="panel w-full max-w-3xl max-h-[90vh] overflow-y-auto">
        {/* Header */}
        <div className="sticky top-0 bg-eidos-surface border-b border-eidos-border px-6 py-4 flex items-center justify-between">
          <div>
            <h2 className="text-lg font-bold">⚙️ Configuración</h2>
            <p className="text-xs text-eidos-muted">
              Gestiona tus API keys y el Cerebro Local sin tocar YAML.
            </p>
          </div>
          <button onClick={onClose} className="btn-secondary text-lg px-3 py-1">
            ✕
          </button>
        </div>

        <div className="p-6 space-y-6">
          {/* Mensaje */}
          {message && (
            <div
              className={`p-3 rounded text-sm ${
                message.type === 'success'
                  ? 'bg-eidos-primary/20 border border-eidos-primary text-eidos-primary'
                  : message.type === 'error'
                  ? 'bg-eidos-danger/20 border border-eidos-danger text-eidos-danger'
                  : 'bg-eidos-accent/20 border border-eidos-accent text-eidos-accent'
              }`}
            >
              {message.text}
            </div>
          )}

          {/* Sección: Cerebro Local */}
          <section>
            <h3 className="text-sm font-bold mb-2 flex items-center gap-2">
              🧠 Cerebro Local (Qwen 2.5 3B)
            </h3>
            <p className="text-xs text-eidos-muted mb-3">
              Descarga un modelo de IA local para privacidad total. Ocupa ~2 GB.
              Una vez descargado, EIDOS puede pensar sin internet.
            </p>

            {models.length > 0 ? (
              <div className="space-y-2 mb-3">
                {models.map(m => (
                  <div
                    key={m.id}
                    className="flex items-center justify-between bg-eidos-bg border border-eidos-border rounded p-2 text-sm"
                  >
                    <div>
                      <span className="font-medium">{m.name}</span>
                      <span className="text-eidos-muted ml-2">
                        {m.quantization} · {m.status}
                      </span>
                    </div>
                    {m.size_bytes && (
                      <span className="text-xs text-eidos-muted">
                        {formatBytes(m.size_bytes)}
                      </span>
                    )}
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-xs text-eidos-muted mb-3">
                No hay modelos registrados todavía.
              </p>
            )}

            {/* Barra de progreso de descarga */}
            {downloading && downloadStatus && (
              <div className="mb-3 p-3 bg-eidos-bg border border-eidos-border rounded">
                <div className="flex justify-between text-xs mb-1">
                  <span>
                    {downloadStatus.completed
                      ? '✓ Descarga completada'
                      : downloadStatus.error
                      ? `✗ Error: ${downloadStatus.error}`
                      : '⏳ Descargando...'}
                  </span>
                  <span className="text-eidos-muted">
                    {formatBytes(downloadStatus.received_bytes)} /{' '}
                    {formatBytes(downloadStatus.total_bytes)}
                  </span>
                </div>
                <div className="w-full bg-eidos-border rounded-full h-2">
                  <div
                    className="bg-eidos-primary h-2 rounded-full transition-all duration-300"
                    style={{ width: `${downloadStatus.percent}%` }}
                  />
                </div>
                <div className="text-right text-xs text-eidos-muted mt-1">
                  {downloadStatus.percent}%
                </div>
              </div>
            )}

            <button
              onClick={handleDownloadBrain}
              disabled={downloading}
              className="btn-primary w-full"
            >
              {downloading
                ? 'Descargando...'
                : models.some(m => m.status === 'ready')
                ? '✓ Cerebro Local instalado'
                : '⬇ Descargar Cerebro Local (~2 GB)'}
            </button>
          </section>

          <hr className="border-eidos-border" />

          {/* Sección: API Keys */}
          <section>
            <h3 className="text-sm font-bold mb-2 flex items-center gap-2">
              🔑 API Keys externas
            </h3>
            <p className="text-xs text-eidos-muted mb-3">
              Configura APIs externas para que EIDOS use modelos en la nube.
              Las keys se guardan localmente en{' '}
              <code className="bg-eidos-bg px-1 rounded">.env</code> y nunca se envían a ningún servidor
              salvo al provider elegido.
            </p>

            <div className="space-y-3">
              {providers.map(p => {
                const keyInfo = keys[p.id];
                const isSet = keyInfo?.set;
                return (
                  <div
                    key={p.id}
                    className="bg-eidos-bg border border-eidos-border rounded p-3"
                  >
                    <div className="flex items-start justify-between mb-2">
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="font-medium text-sm">{p.name}</span>
                          {isSet ? (
                            <span className="badge bg-eidos-primary text-black text-xs">
                              ✓ Configurada
                            </span>
                          ) : (
                            <span className="badge bg-eidos-muted text-eidos-text text-xs">
                              Sin configurar
                            </span>
                          )}
                        </div>
                        <p className="text-xs text-eidos-muted mt-1">{p.description}</p>
                        <p className="text-xs text-eidos-muted">
                          Modelo por defecto: <code>{p.default_model}</code>
                        </p>
                        {isSet && (
                          <p className="text-xs text-eidos-muted mt-1">
                            Key actual: <code>{keyInfo.preview}</code>
                          </p>
                        )}
                      </div>
                      <a
                        href={p.docs_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="btn-secondary text-xs whitespace-nowrap"
                      >
                        Obtener key ↗
                      </a>
                    </div>
                    <div className="flex gap-2">
                      <input
                        type="password"
                        value={inputValues[p.env_var] || ''}
                        onChange={e =>
                          setInputValues({ ...inputValues, [p.env_var]: e.target.value })
                        }
                        placeholder={isSet ? '••••••••••••••••' : `Pega tu ${p.env_var} aquí`}
                        className="input flex-1 text-sm"
                        disabled={saving}
                      />
                      <button
                        onClick={() => handleSaveKey(p.env_var)}
                        disabled={saving || !inputValues[p.env_var]?.trim()}
                        className="btn-primary text-sm"
                      >
                        Guardar
                      </button>
                      {isSet && (
                        <button
                          onClick={() => handleClearKey(p.env_var)}
                          disabled={saving}
                          className="btn-danger text-sm"
                        >
                          Borrar
                        </button>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </section>

          <hr className="border-eidos-border" />

          {/* Info de privacidad */}
          <section className="text-xs text-eidos-muted">
            <p className="font-bold text-eidos-text mb-1">🔒 Tu privacidad</p>
            <ul className="list-disc list-inside space-y-1">
              <li>Las API keys se guardan SOLO en <code>.env</code> local, nunca en la nube.</li>
              <li>El Cerebro Local (Qwen 2.5 3B) corre 100% offline en tu dispositivo.</li>
              <li>Si usas APIs externas, EIDOS aplica PrivacyFilter automáticamente (redacta emails, IPs, teléfonos, etc. antes de enviar).</li>
              <li>Puedes borrar cualquier key cuando quieras con el botón "Borrar".</li>
            </ul>
          </section>
        </div>
      </div>
    </div>
  );
}
