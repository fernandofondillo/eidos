import { useEffect, useRef, useState, useCallback } from 'react';

const API_BASE = '';  // mismo origen en prod; proxy en dev

export interface Monologue {
  id: string;
  timestamp: string;
  input_summary: string;
  observation: string;
  hypothesis: string;
  plan: string[];
  risk: string;
  confidence: number;
  backend: string;
}

export interface ChatResponse {
  text: string;
  monologue_id: string;
  route_type: string;
  confidence: number;
  reward_delta: number;
  monologue_backend: string;
  memory_context: any[] | null;
  evolution_event: any | null;
  monologue: Monologue | null;
}

export interface MemoryStats {
  sensory: any;
  episodic: any;
  semantic: any;
  procedural: any;
  metacognitive: any;
}

export interface MeshStatus {
  enabled: boolean;
  node_id?: string;
  role?: string;
  leader_id?: string;
  socket?: string;
  peers?: number;
  arbitrator?: any;
}

export interface MotivationStats {
  session_total_reward: number;
  by_driver: Record<string, { count: number; total_delta: number }>;
  confidence_window_size: number;
  satisfaction_streak: number;
  satisfaction_window: number;
  recent_rewards: any[];
}

export interface EvolutionStats {
  auto_forge_enabled: boolean;
  total_capsules: number;
  favorites: number;
  promotion_candidates: number;
  promotion_threshold: number;
  promotion_window_hours: number;
}

export interface CapsulesData {
  drafts: any[];
  active: any[];
}

// ---------------------------------------------------------------------------
// REST API
// ---------------------------------------------------------------------------

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

export function useEidosApi() {
  const [health, setHealth] = useState<any>(null);
  const [stats, setStats] = useState<MemoryStats | null>(null);
  const [mesh, setMesh] = useState<MeshStatus | null>(null);
  const [motivation, setMotivation] = useState<MotivationStats | null>(null);
  const [evolution, setEvolution] = useState<EvolutionStats | null>(null);
  const [capsules, setCapsules] = useState<CapsulesData | null>(null);
  const [loading, setLoading] = useState(false);

  const refreshAll = useCallback(async () => {
    setLoading(true);
    try {
      const [h, s, m, mo, ev, cap] = await Promise.all([
        apiGet<any>('/api/health').catch(() => null),
        apiGet<MemoryStats>('/api/stats').catch(() => null),
        apiGet<MeshStatus>('/api/mesh/status').catch(() => null),
        apiGet<MotivationStats>('/api/motivation').catch(() => null),
        apiGet<EvolutionStats>('/api/evolution').catch(() => null),
        apiGet<CapsulesData>('/api/capsules').catch(() => null),
      ]);
      setHealth(h);
      setStats(s);
      setMesh(m);
      setMotivation(mo);
      setEvolution(ev);
      setCapsules(cap);
    } finally {
      setLoading(false);
    }
  }, []);

  const sendChat = useCallback(async (message: string, context?: string): Promise<ChatResponse> => {
    return apiPost('/api/chat', { message, context });
  }, []);

  const forgeCapsule = useCallback(async (request: string, forcePending = false) => {
    return apiPost('/api/capsules/forge', { request, force_pending: forcePending });
  }, []);

  const approveDraft = useCallback(async (draftId: string) => {
    return apiPost('/api/capsules/approve', { draft_id: draftId });
  }, []);

  const rejectDraft = useCallback(async (draftId: string) => {
    return apiPost('/api/capsules/reject', { draft_id: draftId });
  }, []);

  useEffect(() => {
    refreshAll();
    const interval = setInterval(refreshAll, 5000); // refresh cada 5s
    return () => clearInterval(interval);
  }, [refreshAll]);

  return {
    health,
    stats,
    mesh,
    motivation,
    evolution,
    capsules,
    loading,
    refreshAll,
    sendChat,
    forgeCapsule,
    approveDraft,
    rejectDraft,
  };
}

// ---------------------------------------------------------------------------
// WebSocket hook
// ---------------------------------------------------------------------------

export function useEidosWebSocket(onMessage: (msg: any) => void) {
  const wsRef = useRef<WebSocket | null>(null);
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.host;
    const wsUrl = `${protocol}//${host}/ws/chat`;

    const connect = () => {
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => setConnected(true);
      ws.onclose = () => {
        setConnected(false);
        // Reconnect after 2s
        setTimeout(connect, 2000);
      };
      ws.onerror = () => ws.close();
      ws.onmessage = (e) => {
        try {
          const msg = JSON.parse(e.data);
          onMessage(msg);
        } catch (err) {
          console.error('WS parse error:', err);
        }
      };
    };

    connect();

    return () => {
      if (wsRef.current) {
        wsRef.current.onclose = null;
        wsRef.current.close();
      }
    };
  }, [onMessage]);

  const send = useCallback((msg: any) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(msg));
    }
  }, []);

  return { connected, send };
}
